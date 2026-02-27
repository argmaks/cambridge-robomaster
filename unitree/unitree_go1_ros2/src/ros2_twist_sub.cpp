#include "rclcpp/rclcpp.hpp"
#include "unitree_legged_sdk/unitree_legged_sdk.h"
#include "geometry_msgs/msg/twist.hpp"

using Twist = geometry_msgs::msg::Twist;

using namespace UNITREE_LEGGED_SDK;
class Custom
{
public:
  Custom() : safe(LeggedType::Go1),
                          udp(HIGHLEVEL, 8090, "192.168.123.161", 8082)
  {
    udp.InitCmdData(cmd);
  }
  void UDPRecv();
  void UDPSend();
  void cmdVelCallback(const Twist::SharedPtr msg);

  Safety safe;
  UDP udp;
  HighCmd cmd = {};
  HighState state = {};

  rclcpp::Subscription<Twist>::SharedPtr sub_cmd_vel;
};

void Custom::UDPRecv()
{
  udp.Recv();
}

void Custom::UDPSend()
{
  udp.Send();
}

void Custom::cmdVelCallback(const Twist::SharedPtr msg)
{
  printf("cmdVelCallback is running!\n");

  printf("cmd_x_vel = %f\n", msg->linear.x);
  printf("cmd_y_vel = %f\n", msg->linear.y);
  printf("cmd_yaw_vel = %f\n", msg->angular.z);

  udp.GetRecv(state);
  //   printf("%d   %f\n", motiontime, state.imu.quaternion[2]);
  cmd.mode = 0; // 0:idle, default stand      1:forced stand     2:walk continuously
  cmd.gaitType = 0;
  cmd.speedLevel = 0;
  cmd.footRaiseHeight = 0;
  cmd.bodyHeight = 0;
  cmd.euler[0] = 0;
  cmd.euler[1] = 0;
  cmd.euler[2] = 0;
  cmd.velocity[0] = 0.0f;
  cmd.velocity[1] = 0.0f;
  cmd.yawSpeed = 0.0f;
  cmd.reserve = 0;

  cmd.mode = 2;
  cmd.gaitType = 1;
  cmd.velocity[0] = msg->linear.x;
  cmd.velocity[1] = -msg->linear.y;
  cmd.yawSpeed = -msg->angular.z;
  cmd.footRaiseHeight = 0.1;

  udp.SetSend(cmd);
}


int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);

    Custom custom;
    
    auto node = rclcpp::Node::make_shared("node_ros2_twist_sub");
    custom.sub_cmd_vel = node->create_subscription<Twist>("cmd_vel", rclcpp::SensorDataQoS(), std::bind(&Custom::cmdVelCallback, &custom, std::placeholders::_1));

    LoopFunc loop_udpSend("udp_send", 0.002, 3, std::bind(&Custom::UDPSend, &custom));
    LoopFunc loop_udpRecv("udp_recv", 0.002, 3, std::bind(&Custom::UDPRecv, &custom));

    loop_udpSend.start();
    loop_udpRecv.start();

    printf("running!\n");

    rclcpp::spin(node);

    rclcpp::shutdown();

    return 0;
}
