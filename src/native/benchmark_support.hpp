#pragma once

#include <cstdint>
#include <fstream>
#include <stdexcept>
#include <string>

namespace balance_trees::benchmark {

inline std::uint64_t peak_rss_kib() {
    // Linux VmHWM belongs to this executable's address space. ru_maxrss can
    // retain a larger high-water mark from before exec (the Python launcher).
    std::ifstream status("/proc/self/status");
    std::string field, ignored;
    while (status >> field) {
        if (field == "VmHWM:") {
            std::uint64_t value = 0;
            status >> value;
            if (value) return value;
            break;
        }
        std::getline(status, ignored);
    }
    throw std::runtime_error("cannot measure VmHWM");
}

} // namespace balance_trees::benchmark
