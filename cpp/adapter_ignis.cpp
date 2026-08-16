#include <cstdint>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace py = pybind11;

namespace {

class DuelAdapter {
 public:
  DuelAdapter(std::string database, std::string scripts)
      : database_(std::move(database)), scripts_(std::move(scripts)) {}

  void reset(const std::vector<uint32_t>&, const std::vector<uint32_t>&,
             const std::vector<uint32_t>& = {},
             const std::vector<uint32_t>& = {}, uint32_t = 0, int = 5,
             const std::vector<uint32_t>& = {},
             const std::vector<uint32_t>& = {}) {
    not_implemented();
  }

  void step(size_t) { not_implemented(); }
  void counts() const { not_implemented(); }
  void cards(uint8_t, uint8_t) const { not_implemented(); }
  void state_key() const { not_implemented(); }

 private:
  [[noreturn]] static void not_implemented() {
    throw std::runtime_error("ignis adapter not implemented");
  }

  std::string database_;
  std::string scripts_;
};

}  // namespace

PYBIND11_MODULE(_ocgcore_ignis, module) {
  module.doc() = "YAPPING adapter for Project Ignis OCGCore";
  py::class_<DuelAdapter>(module, "Duel")
      .def(py::init<std::string, std::string>(), py::arg("database"),
           py::arg("scripts"))
      .def("reset", &DuelAdapter::reset, py::arg("deck0"), py::arg("deck1"),
           py::arg("extra0") = std::vector<uint32_t>{},
           py::arg("extra1") = std::vector<uint32_t>{}, py::arg("seed") = 0,
           py::arg("start_hand") = 5,
           py::arg("set0") = std::vector<uint32_t>{},
           py::arg("set1") = std::vector<uint32_t>{})
      .def("step", &DuelAdapter::step)
      .def("counts", &DuelAdapter::counts)
      .def("cards", &DuelAdapter::cards)
      .def("state_key", &DuelAdapter::state_key);
}
