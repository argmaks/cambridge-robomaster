cmake_minimum_required(VERSION 3.8)
project(unitree_go1_ros2)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(geometry_msgs REQUIRED)

include_directories(
    include
    ${CMAKE_SOURCE_DIR}/lib/unitree_legged_sdk/include/
)

link_directories(${CMAKE_SOURCE_DIR}/lib/unitree_legged_sdk/lib/cpp/arm64)

add_executable(ros2_twist_sub src/ros2_twist_sub.cpp)
target_link_libraries(ros2_twist_sub -pthread libunitree_legged_sdk.a)
ament_target_dependencies(ros2_twist_sub rclcpp geometry_msgs)

install(TARGETS
    ros2_twist_sub
    DESTINATION lib/${PROJECT_NAME}
)

ament_package()
