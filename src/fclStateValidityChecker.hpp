#pragma once

// #include "environment.h"
#include "robot.h"

#include <fcl/fcl.h>

class fclStateValidityChecker
  : public ompl::base::StateValidityChecker
{
public:
  fclStateValidityChecker(
      ompl::base::SpaceInformationPtr si,
      std::shared_ptr<fcl::BroadPhaseCollisionManagerf> environment,
      std::shared_ptr<Robot> robot)
      : StateValidityChecker(si)
      , environment_(environment)
      , robot_(robot)
  {
  }

  bool isValid(const ompl::base::State* state) const override
  {
    if (!si_->satisfiesBounds(state)) {
      return false;
    }

    fcl::CollisionObjectf robot(robot_->getCollisionGeometry(), robot_->getTransform(state));
    fcl::DefaultCollisionData<float> collision_data;
    environment_->collide(&robot, &collision_data, fcl::DefaultCollisionFunction<float>);

    // std::cout << collision_data.result.isCollision() << std::endl;

    return !collision_data.result.isCollision();
  }

private:
  std::shared_ptr<fcl::BroadPhaseCollisionManagerf> environment_;
  std::shared_ptr<Robot> robot_;
};
