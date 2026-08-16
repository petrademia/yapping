#include <algorithm>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <sqlite3.h>

#include "ocgapi.h"
#include "ocgapi_constants.h"

namespace py = pybind11;
namespace fs = std::filesystem;

namespace {

struct Action {
  std::string kind;
  uint32_t card{};
  uint8_t controller{};
  uint8_t location{};
  uint32_t sequence{};
  uint64_t description{};
  int32_t response{};
  std::vector<uint8_t> response_bytes;
  std::vector<uint32_t> cards;
};

struct Location {
  uint8_t controller{};
  uint8_t location{};
  uint32_t sequence{};
  uint32_t position{};
};

class Reader {
 public:
  Reader(const uint8_t* data, size_t size) : current_(data), end_(data + size) {}

  size_t remaining() const { return static_cast<size_t>(end_ - current_); }
  uint8_t u8() { return read<uint8_t>(); }
  uint16_t u16() { return read<uint16_t>(); }
  uint32_t u32() { return read<uint32_t>(); }
  uint64_t u64() { return read<uint64_t>(); }

  Location location() {
    Location value;
    value.controller = u8();
    value.location = u8();
    value.sequence = u32();
    value.position = u32();
    return value;
  }

  void skip(size_t count) {
    require(count);
    current_ += count;
  }

  const uint8_t* cursor() const { return current_; }

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

template <typename T>
void append_le(std::vector<uint8_t>& bytes, T value) {
  const auto offset = bytes.size();
  bytes.resize(offset + sizeof(T));
  std::memcpy(bytes.data() + offset, &value, sizeof(T));
}

// The core reads card selections as an int32 encoding tag, a uint32 count and
// then indices whose width the tag chooses; tag 2 selects single-byte indices.
std::vector<uint8_t> card_response(const std::vector<uint32_t>& indices) {
  for (uint32_t index : indices)
    if (index > 0xff) throw std::runtime_error("card selection is too large to encode");
  std::vector<uint8_t> bytes;
  append_le<int32_t>(bytes, 2);
  append_le<uint32_t>(bytes, static_cast<uint32_t>(indices.size()));
  for (uint32_t index : indices) bytes.push_back(static_cast<uint8_t>(index));
  return bytes;
}

bool requires_response(uint8_t message) {
  switch (message) {
    case MSG_RETRY:
    case MSG_SELECT_BATTLECMD:
    case MSG_SELECT_IDLECMD:
    case MSG_SELECT_EFFECTYN:
    case MSG_SELECT_YESNO:
    case MSG_SELECT_OPTION:
    case MSG_SELECT_CARD:
    case MSG_SELECT_CHAIN:
    case MSG_SELECT_PLACE:
    case MSG_SELECT_POSITION:
    case MSG_SELECT_TRIBUTE:
    case MSG_SORT_CHAIN:
    case MSG_SELECT_COUNTER:
    case MSG_SELECT_SUM:
    case MSG_SELECT_DISFIELD:
    case MSG_SORT_CARD:
    case MSG_SELECT_UNSELECT_CARD:
    case MSG_ROCK_PAPER_SCISSORS:
    case MSG_ANNOUNCE_RACE:
    case MSG_ANNOUNCE_ATTRIB:
    case MSG_ANNOUNCE_CARD:
    case MSG_ANNOUNCE_NUMBER:
      return true;
    default:
      return false;
  }
}

uint64_t splitmix64(uint64_t& state) {
  state += 0x9e3779b97f4a7c15ull;
  uint64_t value = state;
  value = (value ^ (value >> 30)) * 0xbf58476d1ce4e5b9ull;
  value = (value ^ (value >> 27)) * 0x94d049bb133111ebull;
  return value ^ (value >> 31);
}

class IgnisDuelAdapter {
 public:
  IgnisDuelAdapter(std::string database, std::string scripts)
      : database_path_(std::move(database)), script_dir_(std::move(scripts)) {
    if (sqlite3_open_v2(database_path_.c_str(), &database_, SQLITE_OPEN_READONLY, nullptr) != SQLITE_OK)
      throw std::runtime_error("cannot open card database: " + database_path_ + ": " + sqlite3_errmsg(database_));
    const char* sql = "SELECT alias,setcode,type,atk,def,level,race,attribute FROM datas WHERE id=?";
    if (sqlite3_prepare_v2(database_, sql, -1, &card_statement_, nullptr) != SQLITE_OK)
      throw std::runtime_error("cannot prepare card query for " + database_path_ + ": " + sqlite3_errmsg(database_));
  }

  IgnisDuelAdapter(const IgnisDuelAdapter&) = delete;
  IgnisDuelAdapter& operator=(const IgnisDuelAdapter&) = delete;

  ~IgnisDuelAdapter() {
    close_duel();
    if (card_statement_) sqlite3_finalize(card_statement_);
    if (database_) sqlite3_close(database_);
  }

  py::dict reset(const std::vector<uint32_t>& deck0, const std::vector<uint32_t>& deck1,
                 const std::vector<uint32_t>& extra0 = {},
                 const std::vector<uint32_t>& extra1 = {}, uint32_t seed = 0,
                 int start_hand = 5, const std::vector<uint32_t>& set0 = {},
                 const std::vector<uint32_t>& set1 = {}) {
    if (deck0.empty() || deck1.empty()) throw std::invalid_argument("decks must not be empty");
    close_duel();
    errors_.clear();
    events_.clear();
    actions_.clear();
    winner_ = -1;
    phase_ = 0;
    turn_ = 0;

    const OCG_Player team{8000, static_cast<uint32_t>(start_hand), 1};
    OCG_DuelOptions options{};
    // The core rejects an all-zero seed, so the three trailing words are a
    // deterministic expansion of the caller's seed rather than literal zeros.
    uint64_t state = seed;
    options.seed[0] = seed;
    options.seed[1] = splitmix64(state);
    options.seed[2] = splitmix64(state);
    options.seed[3] = splitmix64(state);
    options.flags = DUEL_MODE_MR5 | DUEL_PSEUDO_SHUFFLE;
    options.team1 = team;
    options.team2 = team;
    options.cardReader = &read_card_callback;
    options.payload1 = this;
    options.scriptReader = &read_script_callback;
    options.payload2 = this;
    options.logHandler = &log_callback;
    options.payload3 = this;
    options.cardReaderDone = &read_card_done_callback;
    options.payload4 = this;
    options.enableUnsafeLibraries = 0;

    const int created = OCG_CreateDuel(&duel_, &options);
    if (created != OCG_DUEL_CREATION_SUCCESS || !duel_) {
      duel_ = nullptr;
      throw std::runtime_error("OCGCore failed to create duel: status " + std::to_string(created));
    }
    // A duel whose bootstrap scripts are missing would answer queries about a
    // board no card effect can ever touch, so tear it down rather than expose it.
    for (const char* bootstrap : {"constant.lua", "utility.lua"})
      if (!read_script(bootstrap, duel_)) {
        close_duel();
        throw std::runtime_error(std::string("cannot load Ignis script ") + bootstrap +
                                 " from " + script_dir_.string());
      }

    load_deck(deck0, 0);
    load_deck(deck1, 1);
    load_extra(extra0, 0);
    load_extra(extra1, 1);
    load_set_cards(set0, 0);
    load_set_cards(set1, 1);
    OCG_StartDuel(duel_);
    advance();
    return decision();
  }

  py::dict step(size_t action_index) {
    if (!duel_) throw std::runtime_error("reset() must be called before step()");
    if (action_index >= actions_.size()) throw std::out_of_range("action index out of range");
    const Action action = actions_[action_index];
    actions_.clear();
    if (action.response_bytes.empty())
      respond(action.response);
    else
      OCG_DuelSetResponse(duel_, action.response_bytes.data(),
                          static_cast<uint32_t>(action.response_bytes.size()));
    advance();
    return decision();
  }

  py::dict counts() const {
    ensure_duel();
    py::dict result;
    for (uint8_t player = 0; player < 2; ++player) {
      const std::string suffix = std::to_string(player);
      result[py::str("deck" + suffix)] = OCG_DuelQueryCount(duel_, player, LOCATION_DECK);
      result[py::str("hand" + suffix)] = OCG_DuelQueryCount(duel_, player, LOCATION_HAND);
      result[py::str("monster" + suffix)] = OCG_DuelQueryCount(duel_, player, LOCATION_MZONE);
      result[py::str("spell_trap" + suffix)] = OCG_DuelQueryCount(duel_, player, LOCATION_SZONE);
      result[py::str("grave" + suffix)] = OCG_DuelQueryCount(duel_, player, LOCATION_GRAVE);
    }
    return result;
  }

  std::vector<uint32_t> cards(uint8_t player, uint8_t location) const {
    ensure_duel();
    uint32_t length = 0;
    const OCG_QueryInfo info{QUERY_CODE, player, location, 0, 0};
    const void* buffer = OCG_DuelQueryLocation(duel_, &length, &info);
    if (!buffer || length < sizeof(uint32_t)) return {};
    Reader reader(static_cast<const uint8_t*>(buffer), length);
    const auto payload = reader.u32();
    if (payload != reader.remaining()) throw std::runtime_error("invalid OCGCore card query");
    std::vector<uint32_t> result;
    while (reader.remaining()) {
      const auto size = reader.u16();
      if (size == 0) continue;  // empty zone
      if (size < sizeof(uint32_t)) throw std::runtime_error("invalid OCGCore card query");
      const auto query = reader.u32();
      if (query == QUERY_CODE && size == sizeof(uint32_t) * 2) {
        const auto code = reader.u32();
        if (code) result.push_back(code);
        continue;
      }
      reader.skip(size - sizeof(uint32_t));
    }
    return result;
  }

  py::bytes state_key() const {
    ensure_duel();
    std::string key;
    uint32_t length = 0;
    if (const void* field = OCG_DuelQueryField(duel_, &length))
      key.append(static_cast<const char*>(field), length);
    for (uint8_t player = 0; player < 2; ++player) {
      for (uint32_t location : {LOCATION_DECK, LOCATION_HAND, LOCATION_MZONE,
                                LOCATION_SZONE, LOCATION_GRAVE, LOCATION_REMOVED,
                                LOCATION_EXTRA}) {
        const OCG_QueryInfo info{QUERY_CODE | QUERY_POSITION, player, location, 0, 0};
        uint32_t zone_length = 0;
        const void* zone = OCG_DuelQueryLocation(duel_, &zone_length, &info);
        key.push_back(static_cast<char>(player));
        key.push_back(static_cast<char>(location));
        if (zone) key.append(static_cast<const char*>(zone), zone_length);
      }
    }
    return py::bytes(key);
  }

 private:
  static void read_card_callback(void* payload, uint32_t code, OCG_CardData* data) {
    static_cast<IgnisDuelAdapter*>(payload)->read_card(code, data);
  }

  static void read_card_done_callback(void*, OCG_CardData* data) {
    delete[] data->setcodes;
    data->setcodes = nullptr;
  }

  static int read_script_callback(void* payload, OCG_Duel duel, const char* name) {
    return static_cast<IgnisDuelAdapter*>(payload)->read_script(name, duel);
  }

  static void log_callback(void* payload, const char* message, int type) {
    if (type == OCG_LOG_TYPE_ERROR)
      static_cast<IgnisDuelAdapter*>(payload)->errors_.emplace_back(message ? message : "");
  }

  int read_script(const char* requested, OCG_Duel duel) {
    const fs::path name = fs::path(requested).filename();
    for (const char* subdirectory : {"", "official", "pre-release", "unofficial"}) {
      const fs::path path = *subdirectory ? script_dir_ / subdirectory / name : script_dir_ / name;
      std::ifstream input(path, std::ios::binary);
      if (!input) continue;
      const std::vector<char> source(std::istreambuf_iterator<char>(input), {});
      return OCG_LoadScript(duel, source.data(), static_cast<uint32_t>(source.size()),
                            name.string().c_str());
    }
    return 0;
  }

  void read_card(uint32_t code, OCG_CardData* data) {
    sqlite3_reset(card_statement_);
    sqlite3_clear_bindings(card_statement_);
    sqlite3_bind_int64(card_statement_, 1, code);
    if (sqlite3_step(card_statement_) != SQLITE_ROW) return;
    data->code = code;
    data->alias = static_cast<uint32_t>(sqlite3_column_int64(card_statement_, 0));
    data->setcodes = make_setcodes(static_cast<uint64_t>(sqlite3_column_int64(card_statement_, 1)));
    data->type = static_cast<uint32_t>(sqlite3_column_int64(card_statement_, 2));
    data->attack = sqlite3_column_int(card_statement_, 3);
    data->defense = sqlite3_column_int(card_statement_, 4);
    const auto level = static_cast<uint32_t>(sqlite3_column_int64(card_statement_, 5));
    data->level = level & 0xff;
    data->lscale = (level >> 24) & 0xff;
    data->rscale = (level >> 16) & 0xff;
    data->race = static_cast<uint64_t>(sqlite3_column_int64(card_statement_, 6));
    data->attribute = static_cast<uint32_t>(sqlite3_column_int64(card_statement_, 7));
    if (data->type & TYPE_LINK) {
      data->link_marker = static_cast<uint32_t>(data->defense);
      data->defense = 0;
    }
  }

  static uint16_t* make_setcodes(uint64_t packed) {
    if (!packed) return nullptr;
    auto* setcodes = new uint16_t[5]{};
    size_t count = 0;
    for (int shift = 0; shift < 64; shift += 16) {
      const auto value = static_cast<uint16_t>((packed >> shift) & 0xffff);
      if (value) setcodes[count++] = value;
    }
    setcodes[count] = 0;
    return setcodes;
  }

  void new_card(uint32_t code, uint8_t player, uint32_t location, uint32_t sequence) {
    const OCG_NewCardInfo info{player, 0, code, player, location, sequence, POS_FACEDOWN_DEFENSE};
    OCG_DuelNewCard(duel_, &info);
  }

  void load_deck(const std::vector<uint32_t>& deck, uint8_t player) {
    for (auto card = deck.rbegin(); card != deck.rend(); ++card)
      new_card(*card, player, LOCATION_DECK, 0);
  }

  void load_extra(const std::vector<uint32_t>& extra, uint8_t player) {
    for (auto card = extra.rbegin(); card != extra.rend(); ++card)
      new_card(*card, player, LOCATION_EXTRA, 0);
  }

  void load_set_cards(const std::vector<uint32_t>& cards, uint8_t player) {
    for (uint32_t sequence = 0; sequence < cards.size(); ++sequence)
      new_card(cards[sequence], player, LOCATION_SZONE, sequence);
  }

  void respond(int32_t value) {
    std::vector<uint8_t> bytes;
    append_le<int32_t>(bytes, value);
    OCG_DuelSetResponse(duel_, bytes.data(), static_cast<uint32_t>(bytes.size()));
  }

  void advance() {
    for (int iterations = 0; iterations < 10000; ++iterations) {
      const int status = OCG_DuelProcess(duel_);
      uint32_t length = 0;
      void* message = OCG_DuelGetMessage(duel_, &length);
      if (length && message) {
        const auto* bytes = static_cast<const uint8_t*>(message);
        if (decode(std::vector<uint8_t>(bytes, bytes + length))) return;
      }
      if (!errors_.empty()) {
        // Drain the log so a later step() reports its own failure, not this one.
        const std::string reason = errors_.back();
        errors_.clear();
        throw std::runtime_error(reason);
      }
      if (status == OCG_DUEL_STATUS_END) return;
      if (status == OCG_DUEL_STATUS_AWAITING && actions_.empty()) continue;
      if (status == OCG_DUEL_STATUS_CONTINUE) continue;
    }
    throw std::runtime_error("OCGCore processing did not settle");
  }

  // The Ignis core frames every message with a uint32 length, so informational
  // messages need no per-message payload sizes to be skipped.
  bool decode(const std::vector<uint8_t>& buffer) {
    Reader frames(buffer.data(), buffer.size());
    while (frames.remaining()) {
      const auto length = frames.u32();
      const uint8_t* payload = frames.cursor();
      frames.skip(length);
      if (!length) continue;
      Reader reader(payload, length);
      const uint8_t message = reader.u8();
      events_.push_back(message);
      switch (message) {
        case MSG_SELECT_IDLECMD:
          decode_idle(reader);
          return true;
        case MSG_SELECT_CHAIN:
          if (decode_chain(reader)) return true;
          respond(-1);
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
        case MSG_WIN:
          winner_ = reader.u8();
          break;
        case MSG_NEW_TURN:
          turn_++;
          break;
        case MSG_NEW_PHASE:
          phase_ = reader.u16();
          break;
        default:
          if (requires_response(message))
            throw std::runtime_error("unsupported OCGCore message " + std::to_string(message));
          break;
      }
    }
    return false;
  }

  void decode_idle(Reader& reader) {
    selecting_player_ = reader.u8();
    const char* kinds[] = {"summon", "special_summon", "reposition", "monster_set", "set", "activate"};
    for (uint32_t command = 0; command < 6; ++command) {
      const auto count = reader.u32();
      for (uint32_t index = 0; index < count; ++index) {
        Action action;
        action.kind = kinds[command];
        action.card = reader.u32();
        action.controller = reader.u8();
        action.location = reader.u8();
        // Only the reposition group writes a single-byte sequence.
        action.sequence = command == 2 ? reader.u8() : reader.u32();
        if (command == 5) {
          action.description = reader.u64();
          reader.skip(1);
        }
        action.response = static_cast<int32_t>((index << 16) | command);
        actions_.push_back(std::move(action));
      }
    }
    if (reader.u8()) actions_.push_back(Action{"battle_phase", 0, 0, 0, 0, 0, 6});
    if (reader.u8()) actions_.push_back(Action{"end_phase", 0, 0, 0, 0, 0, 7});
    if (reader.u8()) actions_.push_back(Action{"shuffle", 0, 0, 0, 0, 0, 8});
  }

  bool decode_chain(Reader& reader) {
    selecting_player_ = reader.u8();
    reader.skip(1);
    const bool forced = reader.u8() != 0;
    reader.skip(4 + 4);
    const auto count = reader.u32();
    for (uint32_t index = 0; index < count; ++index) {
      Action action;
      action.kind = "chain";
      action.card = reader.u32();
      const Location where = reader.location();
      action.controller = where.controller;
      action.location = where.location;
      action.sequence = where.sequence;
      action.description = reader.u64();
      reader.skip(1);
      action.response = static_cast<int32_t>(index);
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
      reader.location();
    }
    const uint64_t description = reader.u64();
    actions_.push_back(Action{"yes", card, 0, 0, 0, description, 1});
    actions_.push_back(Action{"no", card, 0, 0, 0, description, 0});
  }

  void decode_options(Reader& reader) {
    selecting_player_ = reader.u8();
    const int count = reader.u8();
    for (int index = 0; index < count; ++index)
      actions_.push_back(Action{"option", 0, 0, 0, 0, reader.u64(), index});
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
        action.sequence = static_cast<uint32_t>(sequence_offset + zone);
        // Zone placement answers with a raw (controller, location, sequence) triple.
        action.response_bytes = {controller, location, static_cast<uint8_t>(action.sequence)};
        actions_.push_back(std::move(action));
      }
    };
    const uint8_t self = static_cast<uint8_t>(selecting_player_);
    const uint8_t opponent = static_cast<uint8_t>(1 - selecting_player_);
    add_zones(allowed, self, LOCATION_MZONE, 0, 7);
    add_zones(allowed, self, LOCATION_SZONE, 8, 6);
    add_zones(allowed, self, LOCATION_SZONE, 14, 2, 6);
    add_zones(allowed, opponent, LOCATION_MZONE, 16, 7);
    add_zones(allowed, opponent, LOCATION_SZONE, 24, 6);
    add_zones(allowed, opponent, LOCATION_SZONE, 30, 2, 6);
  }

  void decode_single_card(Reader& reader, bool tribute) {
    selecting_player_ = reader.u8();
    reader.skip(1);
    const auto minimum = reader.u32();
    const auto maximum = reader.u32();
    const auto count = reader.u32();
    struct Candidate {
      uint32_t card;
      uint8_t controller;
      uint8_t location;
      uint32_t sequence;
      uint32_t weight;
    };
    std::vector<Candidate> candidates;
    for (uint32_t index = 0; index < count; ++index) {
      Candidate candidate;
      candidate.card = reader.u32();
      if (tribute) {
        candidate.controller = reader.u8();
        candidate.location = reader.u8();
        candidate.sequence = reader.u32();
        candidate.weight = reader.u8();
      } else {
        const Location where = reader.location();
        candidate.controller = where.controller;
        candidate.location = where.location;
        candidate.sequence = where.sequence;
        candidate.weight = 1;
      }
      candidates.push_back(candidate);
    }
    if (minimum == 1 && maximum == 1) {
      for (uint32_t index = 0; index < count; ++index) {
        const auto& candidate = candidates[index];
        Action action;
        action.kind = tribute ? "tribute" : "select_card";
        action.card = candidate.card;
        action.controller = candidate.controller;
        action.location = candidate.location;
        action.sequence = candidate.sequence;
        action.response_bytes = card_response({index});
        actions_.push_back(std::move(action));
      }
      return;
    }
    std::vector<uint32_t> selected;
    const auto enumerate = [&](const auto& self, uint32_t start, uint32_t weight) -> void {
      if (weight >= minimum) {
        Action action;
        action.kind = tribute ? "tribute_cards" : "select_cards";
        if (!selected.empty()) action.card = candidates[selected.front()].card;
        for (uint32_t index : selected) action.cards.push_back(candidates[index].card);
        action.response_bytes = card_response(selected);
        actions_.push_back(std::move(action));
      }
      if (selected.size() == maximum) return;
      for (uint32_t index = start; index < count; ++index) {
        selected.push_back(index);
        self(self, index + 1, weight + candidates[index].weight);
        selected.pop_back();
      }
    };
    enumerate(enumerate, 0, 0);
    if (actions_.empty()) throw std::runtime_error("card selection has no legal subsets");
  }

  static std::vector<int> sum_values(uint32_t parameter) {
    std::vector<int> values{static_cast<int>(parameter & 0xffff)};
    const int alternate = static_cast<int>(parameter >> 16);
    if (alternate && alternate != values[0]) values.push_back(alternate);
    return values;
  }

  void decode_sum(Reader& reader) {
    selecting_player_ = reader.u8();
    const bool at_least = reader.u8() != 0;
    const int target = static_cast<int>(reader.u32());
    const auto minimum = reader.u32();
    const auto maximum = reader.u32();
    const auto mandatory_count = reader.u32();
    std::vector<int> totals{0};
    std::vector<uint32_t> mandatory_cards;
    for (uint32_t index = 0; index < mandatory_count; ++index) {
      mandatory_cards.push_back(reader.u32());
      reader.location();
      const auto values = sum_values(reader.u32());
      std::vector<int> next;
      for (int total : totals)
        for (int value : values) next.push_back(total + value);
      totals = std::move(next);
    }
    const auto count = reader.u32();
    const bool count_ok = minimum <= 1 && maximum >= 1;
    for (uint32_t index = 0; index < count; ++index) {
      Action action;
      action.kind = "select_sum";
      action.card = reader.u32();
      const Location where = reader.location();
      action.controller = where.controller;
      action.location = where.location;
      action.sequence = where.sequence;
      const auto values = sum_values(reader.u32());
      bool sum_ok = false;
      for (int total : totals)
        for (int value : values)
          sum_ok |= at_least ? total + value >= target : total + value == target;
      if (!count_ok || !sum_ok) continue;
      action.cards = mandatory_cards;
      action.cards.push_back(action.card);
      action.response_bytes = card_response({index});
      actions_.push_back(std::move(action));
    }
    if (actions_.empty()) throw std::runtime_error("multi-card sum selection is not implemented yet");
  }

  void decode_select_unselect(Reader& reader) {
    selecting_player_ = reader.u8();
    const bool finishable = reader.u8() != 0;
    const bool cancelable = reader.u8() != 0;
    reader.skip(4 + 4);
    uint32_t response_index = 0;
    const auto decode_cards = [&](uint32_t count, const char* kind) {
      for (uint32_t index = 0; index < count; ++index, ++response_index) {
        Action action;
        action.kind = kind;
        action.card = reader.u32();
        const Location where = reader.location();
        action.controller = where.controller;
        action.location = where.location;
        action.sequence = where.sequence;
        append_le<int32_t>(action.response_bytes, 1);
        append_le<int32_t>(action.response_bytes, static_cast<int32_t>(response_index));
        actions_.push_back(std::move(action));
      }
    };
    decode_cards(reader.u32(), "select_toggle");
    decode_cards(reader.u32(), "unselect_toggle");
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
      OCG_DestroyDuel(duel_);
      duel_ = nullptr;
    }
  }

  void ensure_duel() const {
    if (!duel_) throw std::runtime_error("duel is not active");
  }

  std::string database_path_;
  fs::path script_dir_;
  sqlite3* database_{};
  sqlite3_stmt* card_statement_{};
  OCG_Duel duel_{};
  std::vector<std::string> errors_;
  std::vector<uint8_t> events_;
  std::vector<Action> actions_;
  int selecting_player_{};
  int winner_{-1};
  int turn_{};
  int phase_{};
};

}  // namespace

PYBIND11_MODULE(_ocgcore_ignis, module) {
  module.doc() = "YAPPING adapter for Project Ignis OCGCore";
  py::class_<IgnisDuelAdapter>(module, "Duel")
      .def(py::init<std::string, std::string>(), py::arg("database"),
           py::arg("scripts"))
      .def("reset", &IgnisDuelAdapter::reset, py::arg("deck0"), py::arg("deck1"),
           py::arg("extra0") = std::vector<uint32_t>{},
           py::arg("extra1") = std::vector<uint32_t>{}, py::arg("seed") = 0,
           py::arg("start_hand") = 5,
           py::arg("set0") = std::vector<uint32_t>{},
           py::arg("set1") = std::vector<uint32_t>{})
      .def("step", &IgnisDuelAdapter::step)
      .def("counts", &IgnisDuelAdapter::counts)
      .def("cards", &IgnisDuelAdapter::cards)
      .def("state_key", &IgnisDuelAdapter::state_key);
}
