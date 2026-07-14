#include <algorithm>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <sqlite3.h>

#include "card_data.h"
#include "common.h"
#include "ocgapi.h"

namespace py = pybind11;
namespace fs = std::filesystem;

namespace {

struct Action {
  std::string kind;
  uint32_t card{};
  uint8_t controller{};
  uint8_t location{};
  uint8_t sequence{};
  uint32_t description{};
  int32_t response{};
  std::vector<uint8_t> response_bytes;
  std::vector<uint32_t> cards;
};

class Reader {
 public:
  Reader(const uint8_t* data, size_t size) : current_(data), end_(data + size) {}

  size_t remaining() const { return static_cast<size_t>(end_ - current_); }
  uint8_t u8() { return read<uint8_t>(); }
  uint16_t u16() { return read<uint16_t>(); }
  uint32_t u32() { return read<uint32_t>(); }
  void skip(size_t count) {
    require(count);
    current_ += count;
  }

 private:
  template <typename T>
  T read() {
    require(sizeof(T));
    T value;
    std::memcpy(&value, current_, sizeof(T));
    current_ += sizeof(T);
    return value;
  }

  void require(size_t count) const {
    if (remaining() < count) throw std::runtime_error("truncated OCGCore message");
  }

  const uint8_t* current_;
  const uint8_t* end_;
};

class DuelAdapter;
DuelAdapter* active_adapter = nullptr;

class DuelAdapter {
 public:
  DuelAdapter(std::string database, std::string scripts)
      : database_path_(std::move(database)), script_dir_(std::move(scripts)) {
    if (active_adapter) throw std::runtime_error("only one OCGCore adapter may be active");
    if (sqlite3_open_v2(database_path_.c_str(), &database_, SQLITE_OPEN_READONLY, nullptr) != SQLITE_OK)
      throw std::runtime_error("cannot open card database: " + database_path_);
    const char* sql = "SELECT alias,setcode,type,atk,def,level,race,attribute FROM datas WHERE id=?";
    if (sqlite3_prepare_v2(database_, sql, -1, &card_statement_, nullptr) != SQLITE_OK)
      throw std::runtime_error("cannot prepare card query");
    active_adapter = this;
    set_script_reader(&read_script_callback);
    set_card_reader(&read_card_callback);
    set_message_handler(&message_callback);
  }

  ~DuelAdapter() {
    close_duel();
    if (card_statement_) sqlite3_finalize(card_statement_);
    if (database_) sqlite3_close(database_);
    if (active_adapter == this) active_adapter = nullptr;
  }

  py::dict reset(const std::vector<uint32_t>& deck0, const std::vector<uint32_t>& deck1,
                 const std::vector<uint32_t>& extra0 = {},
                 const std::vector<uint32_t>& extra1 = {}, uint32_t seed = 0,
                 int start_hand = 5) {
    if (deck0.empty() || deck1.empty()) throw std::invalid_argument("decks must not be empty");
    close_duel();
    errors_.clear();
    events_.clear();
    actions_.clear();
    winner_ = -1;
    phase_ = 0;
    turn_ = 0;

    duel_ = create_duel(seed);
    if (!duel_) throw std::runtime_error("OCGCore failed to create duel");
    set_player_info(duel_, 0, 8000, start_hand, 1);
    set_player_info(duel_, 1, 8000, start_hand, 1);
    load_deck(deck0, 0);
    load_deck(deck1, 1);
    load_extra(extra0, 0);
    load_extra(extra1, 1);
    start_duel(duel_, (CURRENT_RULE << 16) | DUEL_PSEUDO_SHUFFLE);
    advance();
    return decision();
  }

  py::dict step(size_t action_index) {
    if (!duel_) throw std::runtime_error("reset() must be called before step()");
    if (action_index >= actions_.size()) throw std::out_of_range("action index out of range");
    const Action action = actions_[action_index];
    actions_.clear();
    if (action.response_bytes.empty()) {
      set_responsei(duel_, action.response);
    } else {
      uint8_t response[SIZE_RETURN_VALUE]{};
      std::copy(action.response_bytes.begin(), action.response_bytes.end(), response);
      set_responseb(duel_, response);
    }
    advance();
    return decision();
  }

  py::dict counts() const {
    ensure_duel();
    py::dict result;
    for (int player = 0; player < 2; ++player) {
      const std::string suffix = std::to_string(player);
      result[py::str("deck" + suffix)] = query_field_count(duel_, player, LOCATION_DECK);
      result[py::str("hand" + suffix)] = query_field_count(duel_, player, LOCATION_HAND);
      result[py::str("monster" + suffix)] = query_field_count(duel_, player, LOCATION_MZONE);
      result[py::str("spell_trap" + suffix)] = query_field_count(duel_, player, LOCATION_SZONE);
      result[py::str("grave" + suffix)] = query_field_count(duel_, player, LOCATION_GRAVE);
    }
    return result;
  }

  std::vector<uint32_t> cards(uint8_t player, uint8_t location) const {
    ensure_duel();
    std::vector<uint8_t> buffer(SIZE_MESSAGE_BUFFER);
    const int length = query_field_card(duel_, player, location, QUERY_CODE,
                                        buffer.data(), 0);
    Reader reader(buffer.data(), length);
    std::vector<uint32_t> result;
    while (reader.remaining()) {
      const auto record_length = reader.u32();
      if (record_length == LEN_EMPTY) continue;
      if (record_length < 12 || record_length - 4 > reader.remaining())
        throw std::runtime_error("invalid OCGCore card query");
      const auto flags = reader.u32();
      const auto code = flags & QUERY_CODE ? reader.u32() : 0;
      if (record_length > 12) reader.skip(record_length - 12);
      if (code) result.push_back(code);
    }
    return result;
  }

  py::bytes state_key() const {
    ensure_duel();
    std::vector<uint8_t> buffer(SIZE_MESSAGE_BUFFER);
    const int length = query_field_info(duel_, buffer.data());
    return py::bytes(reinterpret_cast<const char*>(buffer.data()), length);
  }

 private:
  static byte* read_script_callback(const char* requested, int* length) {
    return active_adapter ? active_adapter->read_script(requested, length) : nullptr;
  }

  static uint32_t read_card_callback(uint32_t code, card_data* data) {
    if (active_adapter) active_adapter->read_card(code, data);
    return 0;
  }

  static uint32_t message_callback(intptr_t duel, uint32_t) {
    if (active_adapter) {
      char message[256]{};
      get_log_message(duel, message);
      active_adapter->errors_.emplace_back(message);
    }
    return 0;
  }

  byte* read_script(const char* requested, int* length) {
    fs::path name(requested);
    fs::path path = script_dir_ / name.filename();
    std::ifstream input(path, std::ios::binary);
    if (!input) {
      *length = 0;
      return nullptr;
    }
    script_buffer_ = std::vector<uint8_t>(std::istreambuf_iterator<char>(input), {});
    *length = static_cast<int>(script_buffer_.size());
    return script_buffer_.data();
  }

  void read_card(uint32_t code, card_data* data) {
    data->clear();
    sqlite3_reset(card_statement_);
    sqlite3_clear_bindings(card_statement_);
    sqlite3_bind_int64(card_statement_, 1, code);
    if (sqlite3_step(card_statement_) != SQLITE_ROW) return;
    data->code = code;
    data->alias = static_cast<uint32_t>(sqlite3_column_int64(card_statement_, 0));
    write_setcode(data->setcode, static_cast<uint64_t>(sqlite3_column_int64(card_statement_, 1)));
    data->type = static_cast<uint32_t>(sqlite3_column_int64(card_statement_, 2));
    data->attack = sqlite3_column_int(card_statement_, 3);
    data->defense = sqlite3_column_int(card_statement_, 4);
    const uint32_t level = static_cast<uint32_t>(sqlite3_column_int64(card_statement_, 5));
    data->level = level & 0xff;
    data->lscale = (level >> 24) & 0xff;
    data->rscale = (level >> 16) & 0xff;
    data->race = static_cast<uint32_t>(sqlite3_column_int64(card_statement_, 6));
    data->attribute = static_cast<uint32_t>(sqlite3_column_int64(card_statement_, 7));
    const bool alternate_artwork = data->alias && data->alias < code + 20 && code < data->alias + 20;
    if (data->alias && !(data->type & TYPE_TOKEN) && !alternate_artwork) {
      data->rule_code = data->alias;
      data->alias = 0;
    }
    if (data->type & TYPE_LINK) {
      data->link_marker = data->defense;
      data->defense = 0;
    }
  }

  void load_deck(const std::vector<uint32_t>& deck, uint8_t player) {
    for (auto card = deck.rbegin(); card != deck.rend(); ++card)
      new_card(duel_, *card, player, player, LOCATION_DECK, 0, POS_FACEDOWN_DEFENSE);
  }

  void load_extra(const std::vector<uint32_t>& extra, uint8_t player) {
    for (auto card = extra.rbegin(); card != extra.rend(); ++card)
      new_card(duel_, *card, player, player, LOCATION_EXTRA, 0, POS_FACEDOWN_DEFENSE);
  }

  void advance() {
    for (int iterations = 0; iterations < 10000; ++iterations) {
      const uint32_t result = process(duel_);
      const int length = result & PROCESSOR_BUFFER_LEN;
      const uint32_t status = result & PROCESSOR_FLAG;
      if (length) {
        std::vector<uint8_t> buffer(length);
        get_message(duel_, buffer.data());
        if (decode(buffer)) return;
      }
      if (!errors_.empty()) throw std::runtime_error(errors_.back());
      if (status == PROCESSOR_END) return;
      if (status == PROCESSOR_WAITING && actions_.empty()) continue;
    }
    throw std::runtime_error("OCGCore processing did not settle");
  }

  bool decode(const std::vector<uint8_t>& buffer) {
    Reader reader(buffer.data(), buffer.size());
    while (reader.remaining()) {
      const uint8_t message = reader.u8();
      events_.push_back(message);
      switch (message) {
        case MSG_SELECT_IDLECMD:
          decode_idle(reader);
          return true;
        case MSG_SELECT_CHAIN:
          if (decode_chain(reader)) return true;
          set_responsei(duel_, -1);
          return false;
        case MSG_SELECT_YESNO:
          decode_yes_no(reader, false);
          return true;
        case MSG_SELECT_EFFECTYN:
          decode_yes_no(reader, true);
          return true;
        case MSG_SELECT_OPTION:
          decode_options(reader);
          return true;
        case MSG_SELECT_POSITION:
          decode_position(reader);
          return true;
        case MSG_SELECT_PLACE:
        case MSG_SELECT_DISFIELD:
          decode_place(reader, message == MSG_SELECT_DISFIELD);
          return true;
        case MSG_SELECT_CARD:
        case MSG_SELECT_TRIBUTE:
          decode_single_card(reader, message == MSG_SELECT_TRIBUTE);
          return true;
        case MSG_SELECT_SUM:
          decode_sum(reader);
          return true;
        case MSG_SELECT_UNSELECT_CARD:
          decode_select_unselect(reader);
          return true;
        case MSG_HINT: reader.skip(6); break;
        case MSG_WIN: winner_ = reader.u8(); reader.skip(1); break;
        case MSG_NEW_TURN: turn_++; reader.skip(1); break;
        case MSG_NEW_PHASE: phase_ = reader.u16(); break;
        case MSG_DRAW: { reader.skip(1); const auto count = reader.u8(); reader.skip(count * 4); break; }
        case MSG_SHUFFLE_DECK: reader.skip(1); break;
        case MSG_SHUFFLE_HAND: { reader.skip(1); const auto count = reader.u8(); reader.skip(count * 4); break; }
        case MSG_CONFIRM_CARDS: { reader.skip(2); const auto count = reader.u8(); reader.skip(count * 7); break; }
        case MSG_MOVE: reader.skip(16); break;
        case MSG_POS_CHANGE: reader.skip(9); break;
        case MSG_SET: reader.skip(8); break;
        case MSG_FIELD_DISABLED: reader.skip(4); break;
        case MSG_CARD_HINT: reader.skip(9); break;
        case MSG_SUMMONING:
        case MSG_SPSUMMONING:
        case MSG_FLIPSUMMONING: reader.skip(8); break;
        case MSG_SUMMONED:
        case MSG_SPSUMMONED:
        case MSG_FLIPSUMMONED:
        case MSG_CHAIN_END: break;
        case MSG_CHAINING: reader.skip(16); break;
        case MSG_CHAINED:
        case MSG_CHAIN_SOLVING:
        case MSG_CHAIN_SOLVED:
        case MSG_CHAIN_NEGATED:
        case MSG_CHAIN_DISABLED: reader.skip(1); break;
        case MSG_BECOME_TARGET: { const auto count = reader.u8(); reader.skip(count * 4); break; }
        case MSG_DAMAGE:
        case MSG_RECOVER:
        case MSG_LPUPDATE:
        case MSG_PAY_LPCOST: reader.skip(5); break;
        default:
          throw std::runtime_error("unsupported OCGCore message " + std::to_string(message));
      }
    }
    return false;
  }

  void decode_idle(Reader& reader) {
    selecting_player_ = reader.u8();
    const char* kinds[] = {"summon", "special_summon", "reposition", "monster_set", "set", "activate"};
    for (int command = 0; command < 6; ++command) {
      const int count = reader.u8();
      for (int index = 0; index < count; ++index) {
        Action action;
        action.kind = kinds[command];
        action.card = reader.u32();
        action.controller = reader.u8();
        action.location = reader.u8();
        action.sequence = reader.u8();
        if (command == 5) action.description = reader.u32();
        action.response = (index << 16) | command;
        actions_.push_back(std::move(action));
      }
    }
    if (reader.u8()) actions_.push_back(Action{"battle_phase", 0, 0, 0, 0, 0, 6});
    if (reader.u8()) actions_.push_back(Action{"end_phase", 0, 0, 0, 0, 0, 7});
    if (reader.u8()) actions_.push_back(Action{"shuffle", 0, 0, 0, 0, 0, 8});
  }

  bool decode_chain(Reader& reader) {
    selecting_player_ = reader.u8();
    const int count = reader.u8();
    reader.skip(1 + 4 + 4);
    bool forced = false;
    for (int index = 0; index < count; ++index) {
      Action action;
      action.kind = "chain";
      reader.skip(1);
      forced |= reader.u8() != 0;
      action.card = reader.u32();
      action.controller = reader.u8();
      action.location = reader.u8();
      action.sequence = reader.u8();
      reader.skip(1);
      action.description = reader.u32();
      action.response = index;
      actions_.push_back(std::move(action));
    }
    if (!forced) actions_.push_back(Action{"pass", 0, 0, 0, 0, 0, -1});
    return !actions_.empty();
  }

  void decode_yes_no(Reader& reader, bool effect) {
    selecting_player_ = reader.u8();
    uint32_t card = 0;
    if (effect) {
      card = reader.u32();
      reader.skip(4);
    }
    const uint32_t description = reader.u32();
    actions_.push_back(Action{"yes", card, 0, 0, 0, description, 1});
    actions_.push_back(Action{"no", card, 0, 0, 0, description, 0});
  }

  void decode_options(Reader& reader) {
    selecting_player_ = reader.u8();
    const int count = reader.u8();
    for (int index = 0; index < count; ++index)
      actions_.push_back(Action{"option", 0, 0, 0, 0, reader.u32(), index});
  }

  void decode_position(Reader& reader) {
    selecting_player_ = reader.u8();
    const uint32_t card = reader.u32();
    const uint8_t positions = reader.u8();
    for (uint8_t position : {POS_FACEUP_ATTACK, POS_FACEDOWN_ATTACK, POS_FACEUP_DEFENSE, POS_FACEDOWN_DEFENSE})
      if (positions & position) actions_.push_back(Action{"position", card, 0, 0, position, 0, position});
  }

  void decode_place(Reader& reader, bool disabled_field) {
    selecting_player_ = reader.u8();
    const uint8_t count = reader.u8();
    if (count > 1) throw std::runtime_error("multi-zone selection is not implemented yet");
    const uint32_t allowed = ~reader.u32();
    const auto add_zones = [&](uint32_t bits, uint8_t controller, uint8_t location,
                               int bit_offset, int zone_count, int sequence_offset = 0) {
      for (int zone = 0; zone < zone_count; ++zone) {
        if (!(bits & (1u << (bit_offset + zone)))) continue;
        Action action;
        action.kind = disabled_field ? "disable_place" : "place";
        action.controller = controller;
        action.location = location;
        action.sequence = static_cast<uint8_t>(sequence_offset + zone);
        action.response_bytes = {controller, location, action.sequence};
        actions_.push_back(std::move(action));
      }
    };
    add_zones(allowed, 0, LOCATION_MZONE, 0, 7);
    add_zones(allowed, 0, LOCATION_SZONE, 8, 6);
    add_zones(allowed, 0, LOCATION_SZONE, 14, 2, 6);
    add_zones(allowed, 1, LOCATION_MZONE, 16, 7);
    add_zones(allowed, 1, LOCATION_SZONE, 24, 6);
    add_zones(allowed, 1, LOCATION_SZONE, 30, 2, 6);
  }

  void decode_single_card(Reader& reader, bool tribute) {
    selecting_player_ = reader.u8();
    reader.skip(1);
    const uint8_t minimum = reader.u8();
    const uint8_t maximum = reader.u8();
    const int count = reader.u8();
    if (minimum != 1 || maximum != 1)
      throw std::runtime_error("multi-card selection is not implemented yet");
    for (int index = 0; index < count; ++index) {
      Action action;
      action.kind = tribute ? "tribute" : "select_card";
      action.card = reader.u32();
      action.controller = reader.u8();
      action.location = reader.u8();
      action.sequence = reader.u8();
      reader.skip(1);
      action.response_bytes = {1, static_cast<uint8_t>(index)};
      actions_.push_back(std::move(action));
    }
  }

  static std::vector<int> sum_values(uint32_t parameter) {
    std::vector<int> values{static_cast<int>(parameter & 0xffff)};
    const int alternate = static_cast<int>(parameter >> 16);
    if (alternate && alternate != values[0]) values.push_back(alternate);
    return values;
  }

  void decode_sum(Reader& reader) {
    const bool at_least = reader.u8() != 0;
    selecting_player_ = reader.u8();
    const int target = static_cast<int>(reader.u32());
    const int minimum = reader.u8();
    const int maximum = reader.u8();
    const int mandatory_count = reader.u8();
    std::vector<int> totals{0};
    std::vector<uint32_t> mandatory_cards;
    for (int index = 0; index < mandatory_count; ++index) {
      mandatory_cards.push_back(reader.u32());
      reader.skip(3);
      const auto values = sum_values(reader.u32());
      std::vector<int> next;
      for (int total : totals)
        for (int value : values) next.push_back(total + value);
      totals = std::move(next);
    }
    const int count = reader.u8();
    for (int index = 0; index < count; ++index) {
      Action action;
      action.kind = "select_sum";
      action.card = reader.u32();
      action.controller = reader.u8();
      action.location = reader.u8();
      action.sequence = reader.u8();
      const auto values = sum_values(reader.u32());
      const int selected_count = mandatory_count + 1;
      const bool count_ok = selected_count >= mandatory_count + minimum
                            && selected_count <= mandatory_count + maximum;
      bool sum_ok = false;
      for (int total : totals)
        for (int value : values)
          sum_ok |= at_least ? total + value >= target : total + value == target;
      if (!count_ok || !sum_ok) continue;
      action.cards = mandatory_cards;
      action.cards.push_back(action.card);
      action.response_bytes.assign(selected_count + 1, 0);
      action.response_bytes[0] = static_cast<uint8_t>(selected_count);
      action.response_bytes[mandatory_count + 1] = static_cast<uint8_t>(index);
      actions_.push_back(std::move(action));
    }
    if (actions_.empty())
      throw std::runtime_error("multi-card sum selection is not implemented yet");
  }

  void decode_select_unselect(Reader& reader) {
    selecting_player_ = reader.u8();
    const bool finishable = reader.u8() != 0;
    const bool cancelable = reader.u8() != 0;
    reader.skip(2);
    int response_index = 0;
    const auto decode_cards = [&](int count, const char* kind) {
      for (int index = 0; index < count; ++index, ++response_index) {
        Action action;
        action.kind = kind;
        action.card = reader.u32();
        action.controller = reader.u8();
        action.location = reader.u8();
        action.sequence = reader.u8();
        reader.skip(1);
        action.response_bytes = {1, static_cast<uint8_t>(response_index)};
        actions_.push_back(std::move(action));
      }
    };
    decode_cards(reader.u8(), "select_toggle");
    decode_cards(reader.u8(), "unselect_toggle");
    if (finishable) actions_.push_back(Action{"finish", 0, 0, 0, 0, 0, -1});
    else if (cancelable) actions_.push_back(Action{"cancel", 0, 0, 0, 0, 0, -1});
  }

  py::dict decision() const {
    py::list actions;
    for (const auto& action : actions_) {
      py::dict value;
      value["kind"] = action.kind;
      value["card"] = action.card;
      value["controller"] = action.controller;
      value["location"] = action.location;
      value["sequence"] = action.sequence;
      value["description"] = action.description;
      value["cards"] = action.cards;
      actions.append(std::move(value));
    }
    py::dict result;
    result["actions"] = std::move(actions);
    result["player"] = selecting_player_;
    result["turn"] = turn_;
    result["phase"] = phase_;
    result["winner"] = winner_ < 0 ? py::none() : py::cast(winner_);
    result["events"] = events_;
    return result;
  }

  void close_duel() {
    if (duel_) {
      end_duel(duel_);
      duel_ = 0;
    }
  }

  void ensure_duel() const {
    if (!duel_) throw std::runtime_error("duel is not active");
  }

  std::string database_path_;
  fs::path script_dir_;
  sqlite3* database_{};
  sqlite3_stmt* card_statement_{};
  intptr_t duel_{};
  std::vector<uint8_t> script_buffer_;
  std::vector<std::string> errors_;
  std::vector<uint8_t> events_;
  std::vector<Action> actions_;
  int selecting_player_{};
  int winner_{-1};
  int turn_{};
  int phase_{};
};

}  // namespace

PYBIND11_MODULE(_ocgcore, module) {
  module.doc() = "Original YAPPING adapter for Fluorohydride OCGCore";
  py::class_<DuelAdapter>(module, "Duel")
      .def(py::init<std::string, std::string>(), py::arg("database"), py::arg("scripts"))
      .def("reset", &DuelAdapter::reset, py::arg("deck0"), py::arg("deck1"),
           py::arg("extra0") = std::vector<uint32_t>{},
           py::arg("extra1") = std::vector<uint32_t>{}, py::arg("seed") = 0,
           py::arg("start_hand") = 5)
      .def("step", &DuelAdapter::step)
      .def("counts", &DuelAdapter::counts)
      .def("cards", &DuelAdapter::cards)
      .def("state_key", &DuelAdapter::state_key);
}
