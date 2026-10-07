cmake_minimum_required(VERSION 4.3)

project(blackkeys-assets-bo LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

find_program(CCACHE_PROGRAM ccache)
if(CCACHE_PROGRAM)
  set(CMAKE_CXX_COMPILER_LAUNCHER
    ${CMAKE_COMMAND} -E env
    CCACHE_SLOPPINESS=pch_defines,time_macros
    "CCACHE_BASEDIR=${CMAKE_SOURCE_DIR}"
    "${CCACHE_PROGRAM}")
endif()

option(ASSETSBO_TEST "Build tests" OFF)

find_package(OpenSSL REQUIRED COMPONENTS Crypto)
find_package(Drogon CONFIG REQUIRED)
find_package(AWSSDK REQUIRED COMPONENTS s3)
find_package(Parquet CONFIG REQUIRED)

add_executable(
  blackkeys-assets-bo
  src/assetsbo.cc
  src/blackkeys/assetsbo/core/node_exporter.cpp
  src/blackkeys/assetsbo/core/settings.cpp
  src/blackkeys/assetsbo/storage/listing.cpp
  src/blackkeys/assetsbo/storage/s3.cpp
  src/blackkeys/assetsbo/storage/parquet_table.cpp
  src/blackkeys/assetsbo/storage/parquet_mutation.cpp
  src/blackkeys/assetsbo/storage/timestamp.cpp
  src/blackkeys/assetsbo/storage/overrides.cpp
  src/blackkeys/assetsbo/handling/index/routes.cpp
  src/blackkeys/assetsbo/handling/event/routes/common.cpp
  src/blackkeys/assetsbo/handling/event/routes/events_list.cpp
  src/blackkeys/assetsbo/handling/event/routes/events_create.cpp
  src/blackkeys/assetsbo/handling/event/routes/events_details.cpp
  src/blackkeys/assetsbo/handling/event/routes/events_update.cpp
  src/blackkeys/assetsbo/handling/event/routes/events_delete.cpp
  src/blackkeys/assetsbo/handling/event/routes/events_image.cpp
  src/blackkeys/assetsbo/handling/brand/routes/common.cpp
  src/blackkeys/assetsbo/handling/brand/routes/brands_list.cpp
  src/blackkeys/assetsbo/handling/brand/routes/brands_create.cpp
  src/blackkeys/assetsbo/handling/brand/routes/brands_details.cpp
  src/blackkeys/assetsbo/handling/brand/routes/brands_image.cpp
  src/blackkeys/assetsbo/handling/brand/routes/brands_update.cpp
  src/blackkeys/assetsbo/handling/brand/routes/brands_delete.cpp)

drogon_create_views(
  blackkeys-assets-bo
  ${CMAKE_CURRENT_SOURCE_DIR}/src/blackkeys/assetsbo/handling
  ${CMAKE_CURRENT_BINARY_DIR})

target_include_directories(
  blackkeys-assets-bo PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_link_libraries(
  blackkeys-assets-bo PRIVATE Drogon::Drogon ${AWSSDK_LINK_LIBRARIES} Parquet::parquet_shared)

if(ASSETSBO_TEST)
  find_package(GTest REQUIRED)
  enable_testing()

  add_executable(
    blackkeys-assets-bo-test
    src/blackkeys/assetsbo/core/settings.cpp
    src/blackkeys/assetsbo/core/settings-test.cc
    src/blackkeys/assetsbo/storage/listing.cpp
    src/blackkeys/assetsbo/storage/listing-test.cc
    src/blackkeys/assetsbo/storage/parquet_table.cpp
    src/blackkeys/assetsbo/storage/parquet_table-test.cc
    src/blackkeys/assetsbo/storage/parquet_mutation.cpp
    src/blackkeys/assetsbo/storage/timestamp.cpp
    src/blackkeys/assetsbo/storage/parquet_mutation-test.cc
    src/blackkeys/assetsbo/storage/overrides.cpp
    src/blackkeys/assetsbo/storage/overrides-test.cc)

  target_include_directories(
    blackkeys-assets-bo-test PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
  target_link_libraries(
    blackkeys-assets-bo-test PRIVATE GTest::gtest_main Parquet::parquet_shared
    Jsoncpp_lib)

  include(GoogleTest)
  gtest_discover_tests(blackkeys-assets-bo-test)

  add_executable(
    blackkeys-assets-bo-brand-test
    src/blackkeys/assetsbo/storage/listing.cpp
    src/blackkeys/assetsbo/storage/parquet_table.cpp
    src/blackkeys/assetsbo/storage/parquet_mutation.cpp
    src/blackkeys/assetsbo/storage/timestamp.cpp
    src/blackkeys/assetsbo/storage/overrides.cpp
    src/blackkeys/assetsbo/storage/s3.cpp
    src/blackkeys/assetsbo/handling/brand/routes/common.cpp
    src/blackkeys/assetsbo/handling/brand/routes/brands_list.cpp
    src/blackkeys/assetsbo/handling/brand/routes/brands_create.cpp
    src/blackkeys/assetsbo/handling/brand/routes/brands_details.cpp
    src/blackkeys/assetsbo/handling/brand/routes/brands_image.cpp
    src/blackkeys/assetsbo/handling/brand/routes/brands_update.cpp
    src/blackkeys/assetsbo/handling/brand/routes/brands_delete.cpp
    src/blackkeys/assetsbo/handling/brand/routes/common-test.cc
    src/blackkeys/assetsbo/handling/brand/routes-test.cc)

  drogon_create_views(
    blackkeys-assets-bo-brand-test
    ${CMAKE_CURRENT_SOURCE_DIR}/src/blackkeys/assetsbo/handling
    ${CMAKE_CURRENT_BINARY_DIR}/brand-test-views)

  target_include_directories(
    blackkeys-assets-bo-brand-test PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
  target_link_libraries(
    blackkeys-assets-bo-brand-test PRIVATE
    GTest::gmock_main Drogon::Drogon ${AWSSDK_LINK_LIBRARIES} Parquet::parquet_shared)

  gtest_discover_tests(blackkeys-assets-bo-brand-test)

  add_executable(
    blackkeys-assets-bo-index-test
    src/blackkeys/assetsbo/handling/index/routes.cpp
    src/blackkeys/assetsbo/handling/index/routes-test.cc)

  target_include_directories(
    blackkeys-assets-bo-index-test PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
  target_link_libraries(
    blackkeys-assets-bo-index-test PRIVATE GTest::gmock_main Drogon::Drogon)

  drogon_create_views(
    blackkeys-assets-bo-index-test
    ${CMAKE_CURRENT_SOURCE_DIR}/src/blackkeys/assetsbo/handling/index/template
    ${CMAKE_CURRENT_BINARY_DIR}/index-test-views)
  drogon_create_views(
    blackkeys-assets-bo-index-test
    ${CMAKE_CURRENT_SOURCE_DIR}/src/blackkeys/assetsbo/handling/template
    ${CMAKE_CURRENT_BINARY_DIR}/index-test-views)
  gtest_discover_tests(blackkeys-assets-bo-index-test)

  add_executable(blackkeys-assets-bo-event-test
    src/blackkeys/assetsbo/storage/listing.cpp
    src/blackkeys/assetsbo/storage/parquet_table.cpp
    src/blackkeys/assetsbo/storage/parquet_mutation.cpp
    src/blackkeys/assetsbo/storage/timestamp.cpp
    src/blackkeys/assetsbo/storage/s3.cpp
    src/blackkeys/assetsbo/storage/overrides.cpp
    src/blackkeys/assetsbo/handling/brand/routes/common.cpp
    src/blackkeys/assetsbo/handling/event/routes/common.cpp
    src/blackkeys/assetsbo/handling/event/routes/events_list.cpp
    src/blackkeys/assetsbo/handling/event/routes/events_create.cpp
    src/blackkeys/assetsbo/handling/event/routes/events_details.cpp
    src/blackkeys/assetsbo/handling/event/routes/events_update.cpp
    src/blackkeys/assetsbo/handling/event/routes/events_delete.cpp
    src/blackkeys/assetsbo/handling/event/routes/events_image.cpp
    src/blackkeys/assetsbo/handling/event/routes-test.cc)
  drogon_create_views(blackkeys-assets-bo-event-test
    ${CMAKE_CURRENT_SOURCE_DIR}/src/blackkeys/assetsbo/handling
    ${CMAKE_CURRENT_BINARY_DIR}/event-test-views)
  target_include_directories(blackkeys-assets-bo-event-test PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
  target_link_libraries(blackkeys-assets-bo-event-test PRIVATE
    GTest::gmock_main Drogon::Drogon ${AWSSDK_LINK_LIBRARIES} Parquet::parquet_shared)
  gtest_discover_tests(blackkeys-assets-bo-event-test)
endif()
