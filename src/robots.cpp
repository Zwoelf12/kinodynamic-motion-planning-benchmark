#include "robots.h"

#include <ompl/control/spaces/RealVectorControlSpace.h>
#include <ompl/base/spaces/SE2StateSpace.h>
#include <ompl/tools/config/MagicConstants.h>

namespace ob = ompl::base;
namespace oc = ompl::control;

class RobotCarFirstOrder : public Robot
{
public:
  RobotCarFirstOrder(
    const ompl::base::RealVectorBounds& position_bounds,
    float v_limit,
    float w_limit)
  {
    geom_.emplace_back(new fcl::Boxf(0.5, 0.25, 1.0));

    auto space(std::make_shared<ob::SE2StateSpace>());
    space->setBounds(position_bounds);

    // create a control space
    // R^1: turning speed
    auto cspace(std::make_shared<oc::RealVectorControlSpace>(space, 2));

    // set the bounds for the control space
    ob::RealVectorBounds cbounds(2);
    cbounds.setLow(0, -v_limit);
    cbounds.setHigh(0, v_limit);
    cbounds.setLow(1, -w_limit);
    cbounds.setHigh(1, w_limit);

    cspace->setBounds(cbounds);

    // construct an instance of  space information from this control space
    si_ = std::make_shared<oc::SpaceInformation>(space, cspace);
  }

  void propagate(
    const ompl::base::State *start,
    const ompl::control::Control *control,
    const double duration,
    ompl::base::State *result) override
  {
    auto startTyped = start->as<ob::SE2StateSpace::StateType>();
    const double *ctrl = control->as<ompl::control::RealVectorControlSpace::ControlType>()->values;

    auto resultTyped = result->as<ob::SE2StateSpace::StateType>();

    // use simple Euler integration
    float x = startTyped->getX();
    float y = startTyped->getY();
    float yaw = startTyped->getYaw();
    float remaining_time = duration;
    const float integration_dt = 0.1f;
    do
    {
      float dt = std::min(remaining_time, integration_dt);

      x += ctrl[0] * cosf(yaw) * dt;
      y += ctrl[0] * sinf(yaw) * dt;
      yaw += ctrl[1] * dt;

      remaining_time -= dt;
    } while (remaining_time >= integration_dt);

    // update result

    resultTyped->setX(x);
    resultTyped->setY(y);
    resultTyped->setYaw(yaw);

    // Normalize orientation
    ob::SO2StateSpace SO2;
    SO2.enforceBounds(resultTyped->as<ob::SO2StateSpace::StateType>(1));
  }

  virtual fcl::Transform3f getTransform(
      const ompl::base::State *state,
      size_t /*part*/) override
  {
    auto stateTyped = state->as<ob::SE2StateSpace::StateType>();

    fcl::Transform3f result;
    result = Eigen::Translation<float, 3>(fcl::Vector3f(stateTyped->getX(), stateTyped->getY(), 0));
    float yaw = stateTyped->getYaw();
    result.rotate(Eigen::AngleAxisf(yaw, Eigen::Vector3f::UnitZ()));
    return result;
  }

  virtual void setPosition(ompl::base::State *state, const fcl::Vector3f position) override
  {
    auto stateTyped = state->as<ob::SE2StateSpace::StateType>();
    stateTyped->setX(position(0));
    stateTyped->setY(position(1));
  }
};

////////////////////////////////////////////////////////////////////////////////////////////////

class RobotCarSecondOrder : public Robot
{
public:
  RobotCarSecondOrder(
      const ompl::base::RealVectorBounds &position_bounds,
      float v_limit,      // max velocity in m/s
      float w_limit,      // max angular velocity in rad/s
      float a_limit,      // max accelleration in m/s^2
      float w_dot_limit) // max angular acceleration in rad/s^2
  {
    geom_.emplace_back(new fcl::Boxf(0.5, 0.25, 1.0));

    auto space(std::make_shared<StateSpace>());
    space->setPositionBounds(position_bounds);

    ob::RealVectorBounds vel_bounds(1);
    vel_bounds.setLow(-v_limit);
    vel_bounds.setHigh(v_limit);
    space->setVelocityBounds(vel_bounds);

    ob::RealVectorBounds w_bounds(1);
    w_bounds.setLow(-w_limit);
    w_bounds.setHigh(w_limit);
    space->setAngularVelocityBounds(w_bounds);

    // create a control space
    // R^1: turning speed
    auto cspace(std::make_shared<oc::RealVectorControlSpace>(space, 2));

    // set the bounds for the control space
    ob::RealVectorBounds cbounds(2);
    cbounds.setLow(0, -a_limit);
    cbounds.setHigh(0, a_limit);
    cbounds.setLow(1, -w_dot_limit);
    cbounds.setHigh(1, w_dot_limit);

    cspace->setBounds(cbounds);

    // construct an instance of  space information from this control space
    si_ = std::make_shared<oc::SpaceInformation>(space, cspace);
  }

  void propagate(
      const ompl::base::State *start,
      const ompl::control::Control *control,
      const double duration,
      ompl::base::State *result) override
  {
    auto startTyped = start->as<StateSpace::StateType>();
    const double *ctrl = control->as<ompl::control::RealVectorControlSpace::ControlType>()->values;

    auto resultTyped = result->as<StateSpace::StateType>();

    // use simple Euler integration
    float x = startTyped->getX();
    float y = startTyped->getY();
    float yaw = startTyped->getYaw();
    float v = startTyped->getVelocity();
    float w = startTyped->getAngularVelocity();
    float remaining_time = duration;
    const float integration_dt = 0.1f;
    do
    {
      float dt = std::min(remaining_time, integration_dt);

      x += v * cosf(yaw) * dt;
      y += v * sinf(yaw) * dt;
      yaw += w * dt;
      v += ctrl[0] * dt;
      w += ctrl[1] * dt;

      remaining_time -= dt;
    } while (remaining_time >= integration_dt);

    // update result

    resultTyped->setX(x);
    resultTyped->setY(y);
    resultTyped->setYaw(yaw);
    resultTyped->setVelocity(v);
    resultTyped->setAngularVelocity(w);

    // Normalize orientation
    ob::SO2StateSpace SO2;
    SO2.enforceBounds(resultTyped->as<ob::SO2StateSpace::StateType>(1));
  }

  virtual fcl::Transform3f getTransform(
      const ompl::base::State *state,
      size_t /*part*/) override
  {
    auto stateTyped = state->as<StateSpace::StateType>();

    fcl::Transform3f result;
    result = Eigen::Translation<float, 3>(fcl::Vector3f(stateTyped->getX(), stateTyped->getY(), 0));
    float yaw = stateTyped->getYaw();
    result.rotate(Eigen::AngleAxisf(yaw, Eigen::Vector3f::UnitZ()));
    return result;
  }

  virtual void setPosition(
      ompl::base::State *state,
      const fcl::Vector3f position) override
  {
    auto stateTyped = state->as<ob::SE2StateSpace::StateType>();
    stateTyped->setX(position(0));
    stateTyped->setY(position(1));
  }

protected:
  class StateSpace : public ob::CompoundStateSpace
  {
  public:
    class StateType : public ob::CompoundStateSpace::StateType
    {
    public:
      StateType() = default;

      double getX() const
      {
        return as<ob::RealVectorStateSpace::StateType>(0)->values[0];
      }

      double getY() const
      {
        return as<ob::RealVectorStateSpace::StateType>(0)->values[1];
      }

      double getYaw() const
      {
        return as<ob::SO2StateSpace::StateType>(1)->value;
      }

      double getVelocity() const
      {
        return as<ob::RealVectorStateSpace::StateType>(2)->values[0];
      }

      double getAngularVelocity() const
      {
        return as<ob::RealVectorStateSpace::StateType>(3)->values[0];
      }

      void setX(double x)
      {
        as<ob::RealVectorStateSpace::StateType>(0)->values[0] = x;
      }

      void setY(double y)
      {
        as<ob::RealVectorStateSpace::StateType>(0)->values[1] = y;
      }

      void setYaw(double yaw)
      {
        as<ob::SO2StateSpace::StateType>(1)->value = yaw;
      }

      void setVelocity(double velocity)
      {
        as<ob::RealVectorStateSpace::StateType>(2)->values[0] = velocity;
      }

      void setAngularVelocity(double angularVelocity)
      {
        as<ob::RealVectorStateSpace::StateType>(3)->values[0] = angularVelocity;
      }
    };

    StateSpace()
    {
      setName("CarSO" + getName());
      type_ = ob::STATE_SPACE_TYPE_COUNT + 0;
      addSubspace(std::make_shared<ob::RealVectorStateSpace>(2), 1.0);  // position
      addSubspace(std::make_shared<ob::SO2StateSpace>(), 0.5);          // orientation
      addSubspace(std::make_shared<ob::RealVectorStateSpace>(1), 0.25); // velocity
      addSubspace(std::make_shared<ob::RealVectorStateSpace>(1), 0.25); // angular velocity
      lock();
    }

    ~StateSpace() override = default;

    void setPositionBounds(const ob::RealVectorBounds &bounds)
    {
      as<ob::RealVectorStateSpace>(0)->setBounds(bounds);
    }

    const ob::RealVectorBounds &getPositionBounds() const
    {
      return as<ob::RealVectorStateSpace>(0)->getBounds();
    }

    void setVelocityBounds(const ob::RealVectorBounds &bounds)
    {
      as<ob::RealVectorStateSpace>(2)->setBounds(bounds);
    }

    const ob::RealVectorBounds &getVelocityBounds() const
    {
      return as<ob::RealVectorStateSpace>(2)->getBounds();
    }

    void setAngularVelocityBounds(const ob::RealVectorBounds &bounds)
    {
      as<ob::RealVectorStateSpace>(3)->setBounds(bounds);
    }

    const ob::RealVectorBounds &getAngularVelocityBounds() const
    {
      return as<ob::RealVectorStateSpace>(3)->getBounds();
    }

    ob::State *allocState() const override
    {
      auto *state = new StateType();
      allocStateComponents(state);
      return state;
    }

    void freeState(ob::State *state) const override
    {
      CompoundStateSpace::freeState(state);
    }

    void registerProjections() override
    {
      class DefaultProjection : public ob::ProjectionEvaluator
      {
      public:
        DefaultProjection(const ob::StateSpace *space) : ob::ProjectionEvaluator(space)
        {
        }

        unsigned int getDimension() const override
        {
          return 2;
        }

        void defaultCellSizes() override
        {
          cellSizes_.resize(2);
          bounds_ = space_->as<ob::SE2StateSpace>()->getBounds();
          cellSizes_[0] = (bounds_.high[0] - bounds_.low[0]) / ompl::magic::PROJECTION_DIMENSION_SPLITS;
          cellSizes_[1] = (bounds_.high[1] - bounds_.low[1]) / ompl::magic::PROJECTION_DIMENSION_SPLITS;
        }

        void project(const ob::State *state, Eigen::Ref<Eigen::VectorXd> projection) const override
        {
          projection = Eigen::Map<const Eigen::VectorXd>(
              state->as<ob::SE2StateSpace::StateType>()->as<ob::RealVectorStateSpace::StateType>(0)->values, 2);
        }
      };

      registerDefaultProjection(std::make_shared<DefaultProjection>(this));
    }
  };
};

////////////////////////////////////////////////////////////////////////////////////////////////

class RobotCarFirstOrderWithTrailers : public Robot
{
public:
  RobotCarFirstOrderWithTrailers(
      const ompl::base::RealVectorBounds &position_bounds,
      float v_limit,
      float phi_limit,
      float L,
      const std::vector<float>& hitch_lengths)
      : Robot()
      , L_(L)
      , hitch_lengths_(hitch_lengths)
  {
    geom_.emplace_back(new fcl::Boxf(0.5, 0.25, 1.0));
    for (size_t i = 0; i < hitch_lengths.size(); ++i) {
      geom_.emplace_back(new fcl::Boxf(0.3, 0.25, 1.0));
    }

    auto space(std::make_shared<StateSpace>(hitch_lengths.size()));
    space->setPositionBounds(position_bounds);

    // create a control space
    // R^1: turning speed
    auto cspace(std::make_shared<oc::RealVectorControlSpace>(space, 2));

    // set the bounds for the control space
    ob::RealVectorBounds cbounds(2);
    cbounds.setLow(0, -v_limit);
    cbounds.setHigh(0, v_limit);
    cbounds.setLow(1, -phi_limit);
    cbounds.setHigh(1, phi_limit);

    cspace->setBounds(cbounds);

    // construct an instance of  space information from this control space
    si_ = std::make_shared<oc::SpaceInformation>(space, cspace);
  }

  virtual size_t numParts()
  {
    return hitch_lengths_.size() + 1;
  }

  void propagate(
      const ompl::base::State *start,
      const ompl::control::Control *control,
      const double duration,
      ompl::base::State *result) override
  {
    auto startTyped = start->as<StateSpace::StateType>();
    const double *ctrl = control->as<ompl::control::RealVectorControlSpace::ControlType>()->values;

    auto resultTyped = result->as<StateSpace::StateType>();

    // use simple Euler integration
    float x = startTyped->getX();
    float y = startTyped->getY();
    std::vector<float> theta(hitch_lengths_.size() + 1);
    for (size_t i = 0; i < hitch_lengths_.size() + 1; ++i) {
      theta[i] = startTyped->getTheta(i);
    }
    float remaining_time = duration;
    const float integration_dt = 0.1f;
    do
    {
      float dt = std::min(remaining_time, integration_dt);

      x += ctrl[0] * cosf(theta[0]) * dt;
      y += ctrl[0] * sinf(theta[0]) * dt;
      // TODO: loop over this in reverse, to avoid changing dependenies
      //       (for a single trailer it shouldn't matter)
      for (size_t i = 1; i < hitch_lengths_.size() + 1; ++i) {
        float theta_dot = ctrl[0] / hitch_lengths_[i-i];
        for (size_t j = 1; j < i; ++j) {
          theta_dot *= cosf(theta[j-1] - theta[j]);
        }
        theta_dot *= sinf(theta[i-1] - theta[i]);
        theta[i] += theta_dot * dt;
      }
      theta[0] += ctrl[0] / L_ * tanf(ctrl[1]) * dt;

      remaining_time -= dt;
    } while (remaining_time >= integration_dt);

    // update result
    resultTyped->setX(x);
    resultTyped->setY(y);
    for (size_t i = 0; i < hitch_lengths_.size() + 1; ++i) {
      resultTyped->setTheta(i, theta[i]);
    }
  }

  virtual fcl::Transform3f getTransform(
      const ompl::base::State *state,
      size_t part) override
  {
    auto stateTyped = state->as<StateSpace::StateType>();

    fcl::Transform3f result;

    if (part == 0) {
      result = Eigen::Translation<float, 3>(fcl::Vector3f(stateTyped->getX(), stateTyped->getY(), 0));
      float yaw = stateTyped->getTheta(0);
      result.rotate(Eigen::AngleAxisf(yaw, Eigen::Vector3f::UnitZ()));
    } else if (part == 1) {
      fcl::Vector3f pos0(stateTyped->getX(), stateTyped->getY(), 0);
      float theta1 = stateTyped->getTheta(1);
      fcl::Vector3f delta(cosf(theta1), sinf(theta1), 0);
      result = Eigen::Translation<float, 3>(pos0 - delta * hitch_lengths_[0]);
      result.rotate(Eigen::AngleAxisf(theta1, Eigen::Vector3f::UnitZ()));
    } else {
      assert(false);
    }
    return result;
  }

  virtual void setPosition(ompl::base::State *state, const fcl::Vector3f position) override
  {
    auto stateTyped = state->as<StateSpace::StateType>();
    stateTyped->setX(position(0));
    stateTyped->setY(position(1));
  }

protected:
  class StateSpace : public ob::CompoundStateSpace
  {
  public:
    class StateType : public ob::CompoundStateSpace::StateType
    {
    public:
      StateType() = default;

      double getX() const
      {
        return as<ob::RealVectorStateSpace::StateType>(0)->values[0];
      }

      double getY() const
      {
        return as<ob::RealVectorStateSpace::StateType>(0)->values[1];
      }

      // 0 means theta of pulling car
      double getTheta(size_t trailer) const
      {
        return as<ob::SO2StateSpace::StateType>(1+trailer)->value;
      }

      void setX(double x)
      {
        as<ob::RealVectorStateSpace::StateType>(0)->values[0] = x;
      }

      void setY(double y)
      {
        as<ob::RealVectorStateSpace::StateType>(0)->values[1] = y;
      }

      void setTheta(size_t trailer, double yaw)
      {
        auto s = as<ob::SO2StateSpace::StateType>(1+trailer);
        s->value = yaw;

        // Normalize orientation
        ob::SO2StateSpace SO2;
        SO2.enforceBounds(s);
      }
    };

    StateSpace(size_t numTrailers)
    {
      setName("CarWithTrailerSO" + getName());
      type_ = ob::STATE_SPACE_TYPE_COUNT + 1;
      addSubspace(std::make_shared<ob::RealVectorStateSpace>(2), 1.0);  // position
      addSubspace(std::make_shared<ob::SO2StateSpace>(), 0.5);          // orientation
      for (size_t i = 0; i < numTrailers; ++i) {
        addSubspace(std::make_shared<ob::SO2StateSpace>(), 0.5);        // orientation
      }
      lock();
    }

    ~StateSpace() override = default;

    void setPositionBounds(const ob::RealVectorBounds &bounds)
    {
      as<ob::RealVectorStateSpace>(0)->setBounds(bounds);
    }

    const ob::RealVectorBounds &getPositionBounds() const
    {
      return as<ob::RealVectorStateSpace>(0)->getBounds();
    }

    ob::State *allocState() const override
    {
      auto *state = new StateType();
      allocStateComponents(state);
      return state;
    }

    void freeState(ob::State *state) const override
    {
      CompoundStateSpace::freeState(state);
    }

    void registerProjections() override
    {
      class DefaultProjection : public ob::ProjectionEvaluator
      {
      public:
        DefaultProjection(const ob::StateSpace *space) : ob::ProjectionEvaluator(space)
        {
        }

        unsigned int getDimension() const override
        {
          return 2;
        }

        void defaultCellSizes() override
        {
          cellSizes_.resize(2);
          bounds_ = space_->as<ob::SE2StateSpace>()->getBounds();
          cellSizes_[0] = (bounds_.high[0] - bounds_.low[0]) / ompl::magic::PROJECTION_DIMENSION_SPLITS;
          cellSizes_[1] = (bounds_.high[1] - bounds_.low[1]) / ompl::magic::PROJECTION_DIMENSION_SPLITS;
        }

        void project(const ob::State *state, Eigen::Ref<Eigen::VectorXd> projection) const override
        {
          projection = Eigen::Map<const Eigen::VectorXd>(
              state->as<ob::SE2StateSpace::StateType>()->as<ob::RealVectorStateSpace::StateType>(0)->values, 2);
        }
      };

      registerDefaultProjection(std::make_shared<DefaultProjection>(this));
    }
  };

protected:
  float L_;
  std::vector<float> hitch_lengths_;

};

////////////////////////////////////////////////////////////////////////////////////////////////

std::shared_ptr<Robot> create_robot(
  const std::string &robotType,
  const ob::RealVectorBounds &positionBounds)
{
  std::shared_ptr<Robot> robot;
  if (robotType == "car_first_order_0")
  {
    robot.reset(new RobotCarFirstOrder(
        positionBounds,
        /*v_limit*/ 0.5 /* m/s*/,
        /*w_limit*/ 0.5 /*rad/s*/));
  }
  else if (robotType == "car_second_order_0")
  {
    robot.reset(new RobotCarSecondOrder(
        positionBounds,
        /*v_limit*/ 0.5 /*m/s*/,
        /*w_limit*/ 0.5 /*rad/s*/,
        /*a_limit*/ 2.0 /*m/s^2*/,
        /*w_dot_limit*/ 2.0 /*rad/s^2*/
        ));
  }
  else if (robotType == "car_first_order_with_0_trailers_0")
  {
    robot.reset(new RobotCarFirstOrderWithTrailers(
        positionBounds,
        /*v_limit*/ 0.5 /*m/s*/,
        /*phi_limit*/ M_PI/3.0f /*rad*/,
        /*L*/ 0.4 /*m*/,
        /*hitch_lengths*/ {} /*m*/
        ));
  }
  else if (robotType == "car_first_order_with_1_trailers_0")
  {
    robot.reset(new RobotCarFirstOrderWithTrailers(
        positionBounds,
        /*v_limit*/ 0.5 /*m/s*/,
        /*phi_limit*/ M_PI / 3.0f /*rad*/,
        /*L*/ 0.4 /*m*/,
        /*hitch_lengths*/ {0.5} /*m*/
        ));
  }
  else
  {
    throw std::runtime_error("Unknown robot type!");
  }
  return robot;
}