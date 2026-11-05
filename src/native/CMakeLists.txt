cmake_minimum_required(VERSION 3.16)
project(balance_trees_native LANGUAGES CXX)

add_library(balance_trees tree.cpp)
target_include_directories(balance_trees PUBLIC include)
target_compile_features(balance_trees PUBLIC cxx_std_20)
set_target_properties(balance_trees PROPERTIES CXX_EXTENSIONS OFF)
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(balance_trees PRIVATE -Wall -Wextra -Wpedantic)
endif()

add_executable(balance-tree main.cpp)
target_link_libraries(balance-tree PRIVATE balance_trees)

add_executable(native-benchmark benchmark.cpp)
target_link_libraries(native-benchmark PRIVATE balance_trees)

include(CTest)
if(BUILD_TESTING)
  add_executable(native-tests ../../tests/native/test_tree.cpp)
  target_link_libraries(native-tests PRIVATE balance_trees)
  add_test(NAME native-tree COMMAND native-tests)
endif()
