import numpy as np
from physics.multirotor_models.multirotor_full_model_komo_scp import calc_rot_vel, qrotate, qmultiply, qconjugate
import pickle
import rowan
import yaml
import matplotlib.pyplot as plt

class OptSolution():
    def __init__(self, states, actions, time=None, nu=None, opt_val=None, num_iter=None, tdil=None, time_cvxpy=None, time_cvx_solver=None, constr_viol = 0):
        self.states = states # optimal states
        self.actions = actions # optimal actions
        self.time = time # time needed to solve the problem
        self.nu = nu # dynamic constraint violation for scvx
        self.opt_val = opt_val # optimal problem value
        self.num_iter = num_iter # numbers of iterations until convergence
        self.time_dil = tdil # time dilation for timeoptimal calculation
        self.time_cvxpy = time_cvxpy # time spend in the cvxpy interface
        self.time_cvx_solver = time_cvx_solver # time taken only by the convex solver
        self.constr_viol = constr_viol # constraint violation of KOMO

class Obstacle():
    def __init__(self, type, shape, pos, quat):
        self.type = type # Obstacle type (box, sphere)
        self.shape = shape # shape of Obstacle
        self.pos = pos # position of Obstacle origin
        self.quat = quat # orientation of Obstacle

class Parameter_scvx():
    def __init__(self):
        self.max_num_iter = None # maximum number of iterations
        self.num_time_steps = None # number of time steps

class Parameter_casadi():
    def __init__(self):
        self.num_time_steps = None # number of time steps
        self.discretization_method = None # discretization method
        self.use_c_code = False # choose if pre compiled c code should be used for dynamic function

class Parameter_komo():
    def __init__(self):
        self.phases = None # number of Phases the problem has
        self.time_steps_per_phase = None # number of time steps per phase
        self.time_per_phase = None # time per phase in seconds
        self.noise = None # noise used for initialization

class Opt_processData():
    def __init__(self):
        self.robot = None # used dynamic model
        self.data = None # extracted data
        self.real_traj = None # integrated data
        self.obs = None # list of obstacles
        self.int_err = None # integration error indicating dynamic violations
        self.int_err_small_dt = None # integration error indicating to small stepsize
        self.x0 = None # starting point
        self.xf = None # end point
        self.intermediate_states = None # intermediate states
        self.initial_x = None # initial states
        self.initial_u = None  # initial actions
        self.t_dil = None # optimized time dilation
        self.time = None # time needed to solve the nonconvex problem
        self.time_cvx_solver = None # time needed by the convex solver to solve the convex subproblem

def extract_sol_dI(C, komo, phases, timeStepspP, timepP, startPoint, quad_names):

    n_timesteps = phases*timeStepspP+1 #because initial state is not included
    n_state_elem = komo.getPathFrames().shape[2]
    n_quad_copter = len(quad_names)
    sz = (n_timesteps, n_state_elem, n_quad_copter)
    trajectory_pos = np.zeros(n_timesteps*n_state_elem*n_quad_copter).reshape(*sz)
    dt = timepP / timeStepspP

    for quad_nr in range(len(quad_names)):
        # get copter index
        idx_copter = [idx for idx in range(len(C.getFrameNames())) if quad_names[quad_nr] in C.getFrameNames()[idx]]
        # extract copter positions
        trajectory_pos_quad_nr = komo.getPathFrames()[:, idx_copter[0], :]

        # unnecessary if full model is used
        if len(np.shape(startPoint)) == 1:
            startPoint_simpModel = np.array([startPoint[0], startPoint[1], startPoint[2], 1, 0, 0, 0])
        else:
            startPoint_simpModel = np.array([startPoint[quad_nr, 0], startPoint[quad_nr, 1], startPoint[quad_nr, 2], 1, 0, 0, 0])

        # add initial position
        trajectory_pos[:, :, quad_nr] = np.vstack((startPoint_simpModel, trajectory_pos_quad_nr))

    # calculate velocities according to implicit euler scheme used during the optimization in KOMO
    # first derivative (x(t)-x(t-dt))/dt
    trajectory_vel = (trajectory_pos[1:, :3, :] - trajectory_pos[0:-1, :3, :]) / dt
    trajectory_vel = np.vstack((startPoint[3:6], trajectory_vel[:,:,0])) ### to use more than one quadcopter the indexing in the velocity has to change

    states = np.hstack((trajectory_pos[:, 0:3, 0], trajectory_vel)) ### to use more than one quadcopter the indexing in the velocity has to change
    # second derivative (v(t)-v(t-dt))/dt
    actions = (trajectory_vel[1:, :] - trajectory_vel[0:-1, :]) / dt
    actions = np.vstack((actions, np.zeros(3) * np.nan))

    solution = OptSolution(states, actions, constr_viol=komo.getConstraintViolations())

    return solution

def extract_sol_fM(C, komo, phases, timeStepspP, timepP, startPoint, nrMotors, mc_names):

    # timestep size
    dt = timepP/timeStepspP

    # get nr of timesteps, states, multicopter, actions
    n_timesteps = phases*timeStepspP
    n_states = komo.getPathFrames().shape[2]
    n_multi_copter = len(mc_names)
    n_actions = nrMotors

    # initialize arrays
    sz_s = (n_timesteps, n_states, n_multi_copter)
    trajectory_pos = np.zeros(n_timesteps * n_states * n_multi_copter).reshape(*sz_s)

    sz_a = (n_timesteps + 2, n_actions, n_multi_copter)
    forces = np.zeros((n_timesteps+2) * n_actions * n_multi_copter).reshape(*sz_a)

    sz_w = (n_timesteps, 3, n_multi_copter)
    trajectory_omega = np.zeros(n_timesteps * 3 * n_multi_copter).reshape(sz_w)
    trajectory_vel_lin = np.zeros(n_timesteps * 3 * n_multi_copter).reshape(sz_w)

    # add inital conditions for velocities
    trajectory_omega[0] = startPoint[10:, np.newaxis]
    trajectory_vel_lin[0] = startPoint[3:6, np.newaxis]

    # extract solutions for each multicopter
    for mc_nr in range(len(mc_names)):
        # get copter index
        idx_copter = [idx for idx in range(len(C.getFrameNames())) if mc_names[mc_nr] in C.getFrameNames()[idx]]
        # extract copter positions
        trajectory_pos_mc_nr = komo.getPathFrames()[:, idx_copter[0], :]
        trajectory_pos[:, :, mc_nr] = trajectory_pos_mc_nr

        # extract forces
        forces_mc_nr = np.array([f["force"] for f in komo.getForceInteractions()])
        forces_mc_nr = np.reshape(forces_mc_nr, (-1, n_actions))
        forces[:, :, mc_nr] = forces_mc_nr

        # calculate rotational velocity from quaternions
        for t in range(1, n_timesteps):
            q_tm1 = trajectory_pos[t - 1, 3:, mc_nr]
            q_t = trajectory_pos[t, 3:, mc_nr]

            # avoid sign flip in quaternion
            if np.dot(q_tm1, q_t) < 0:
                qt = -q_t
                #qt[0] = -q_t[0]
                #print("q_tm1: ", q_tm1)
                #print("q_t: ", q_t)
                #print("dot product: ", np.dot(q_tm1, q_t))
            else:
                qt = q_t

            w_t = calc_rot_vel(qt, q_tm1, dt)
            trajectory_omega[t, :, mc_nr] = w_t #qrotate(qconjugate(q_t),w_t)

    # first derivative (x(t)-x(t-dt))/dt to calculate linear velocity at t
    trajectory_vel_lin[1:] = (trajectory_pos[1:, :3] - trajectory_pos[0:-1, :3]) / dt

    # combine positions and velocities
    states = np.hstack((trajectory_pos[:, 0:3, :], trajectory_vel_lin[:, 0:3, :], trajectory_pos[:, 3:,:], trajectory_omega[:,:,:]))
    actions = forces[2:]
    actions[-1] *= np.nan # set unused action to nan

    # to use more than one quadcopter change that
    states = states[:,:,0]
    actions = actions[:,:,0]*(-timeStepspP/timepP) # give actions correct units

    solution = OptSolution(states, actions, constr_viol=komo.getConstraintViolations())

    return solution

#####################

def extract_sol_fM_(C, komo, phases, timeStepspP, timepP, startPoint, nrMotors, mc_names):

    # timestep size
    dt = timepP/timeStepspP
    print("komo dt in extract fm: ", dt)

    # get nr of timesteps, states, multicopter, actions
    n_timesteps = phases*timeStepspP
    n_states = komo.getPathFrames().shape[2]
    n_multi_copter = len(mc_names)
    n_actions = nrMotors

    # initialize arrays
    sz_s = (n_timesteps, n_states, n_multi_copter)
    trajectory_pos = np.zeros(n_timesteps * n_states * n_multi_copter).reshape(*sz_s)

    sz_a = (n_timesteps + 2, n_actions, n_multi_copter)
    forces = np.zeros((n_timesteps+2) * n_actions * n_multi_copter).reshape(*sz_a)

    sz_w = (n_timesteps, 3, n_multi_copter)
    trajectory_omega = np.zeros(n_timesteps * 3 * n_multi_copter).reshape(sz_w)
    trajectory_vel_lin = np.zeros(n_timesteps * 3 * n_multi_copter).reshape(sz_w)

    # add inital conditions for velocities
    trajectory_omega[0] = startPoint[10:, np.newaxis]
    trajectory_vel_lin[0] = startPoint[3:6, np.newaxis]

    # extract solutions for each multicopter
    for mc_nr in range(len(mc_names)):
        # get copter index
        idx_copter = [idx for idx in range(len(C.getFrameNames())) if mc_names[mc_nr] in C.getFrameNames()[idx]]
        # extract copter positions
        trajectory_pos_mc_nr = komo.getPathFrames()[:, idx_copter[0], :]
        trajectory_pos[:, :, mc_nr] = trajectory_pos_mc_nr

        # extract forces
        forces_mc_nr = np.array([f["force"] for f in komo.getForceInteractions()])
        forces_mc_nr = np.reshape(forces_mc_nr, (-1, n_actions))
        forces[:, :, mc_nr] = forces_mc_nr

        # calculate rotational velocity from quaternions
        for t in range(1, n_timesteps):
            q_tm1 = trajectory_pos[t - 1, 3:, mc_nr]
            q_t = trajectory_pos[t, 3:, mc_nr]

            # avoid sign flip in quaternion
            if np.dot(q_tm1, q_t) < 0:
                qt = q_t
                qt[0] = -q_t[0]
            else:
                qt = q_t

            w_t = calc_rot_vel(qt, q_tm1, dt)
            trajectory_omega[t, :, mc_nr] = w_t

    # first derivative (x(t)-x(t-dt))/dt to calculate linear velocity at t
    trajectory_vel_lin[1:] = (trajectory_pos[1:, :3] - trajectory_pos[0:-1, :3]) / dt

    # combine positions and velocities
    states = np.hstack((trajectory_pos[:, 0:3, :], trajectory_vel_lin[:, 0:3, :], trajectory_pos[:, 3:,:], trajectory_omega[:,:,:]))
    actions = forces[2:]
    actions[-1] *= np.nan # set unused action to nan

    # to use more than one quadcopter change that
    states = states[:,:,0]
    actions = actions[:,:,0]*(-timeStepspP/timepP) # give actions correct units
    #act1 = actions[:,3]
    #actions = np.hstack((act1[:,np.newaxis],actions[:,0:3]))

    solution = OptSolution(states, actions, constr_viol=komo.getConstraintViolations())

    return solution

def save_object(filename, sol):
    with open(filename, "wb") as outp:
        pickle.dump(sol, outp, pickle.HIGHEST_PROTOCOL)

def save_opt_output_all(optProb,
                        prob_name,
                        solution_scvx,
                        solution_komo,
                        data_scvx,
                        data_komo,
                        real_traj_scvx,
                        real_traj_komo,
                        int_error_scvx,
                        int_error_small_dt_scvx,
                        int_error_komo,
                        int_error_small_dt_komo):

    opt_processData_scvx = Opt_processData()
    opt_processData_scvx.robot = optProb.robot
    opt_processData_scvx.data = data_scvx
    opt_processData_scvx.real_traj = real_traj_scvx
    opt_processData_scvx.int_err = int_error_scvx
    opt_processData_scvx.int_err_small_dt = int_error_small_dt_scvx
    opt_processData_scvx.obs = optProb.obs
    opt_processData_scvx.x0 = optProb.x0
    opt_processData_scvx.xf = optProb.xf
    opt_processData_scvx.t_dil = solution_scvx.time_dil
    opt_processData_scvx.time = solution_scvx.time
    opt_processData_scvx.time_cvx_solver = solution_scvx.time_cvx_solver

    opt_processData_komo = Opt_processData()
    opt_processData_komo.robot = optProb.robot
    opt_processData_komo.data = data_komo
    opt_processData_komo.real_traj = real_traj_komo
    opt_processData_komo.int_err = int_error_komo
    opt_processData_komo.int_err_small_dt = int_error_small_dt_komo
    opt_processData_komo.obs = optProb.obs
    opt_processData_komo.x0 = optProb.x0
    opt_processData_komo.xf = optProb.xf
    opt_processData_komo.t_dil = solution_komo.time_dil
    opt_processData_komo.time = solution_komo.time

    if optProb.robot.nrMotors == 2:
        prob_name += "_fM_2m"
    elif optProb.robot.nrMotors == 3:
        prob_name += "_fM_3m"
    elif optProb.robot.nrMotors == 4:
        prob_name += "_fM_4m"
    elif optProb.robot.nrMotors == 6:
        prob_name += "_fM_6m"
    else:
        prob_name += "_fM_8m"

    # save data
    path = "data/"

    filename = path + prob_name

    save_object(filename + "_scvx", opt_processData_scvx)
    save_object(filename + "_komo", opt_processData_komo)

def save_opt_output(optProb,
                    prob_name,
                    solution,
                    data,
                    int_error,
                    alg_pars = None):

        opt_processData = Opt_processData()
        opt_processData.robot = optProb.robot
        opt_processData.data = data
        opt_processData.int_err = int_error
        opt_processData.obs = optProb.obs
        opt_processData.x0 = optProb.x0
        opt_processData.xf = optProb.xf
        opt_processData.intermediate_states = optProb.intermediate_states
        opt_processData.initial_x = optProb.initial_x
        opt_processData.initial_u = optProb.initial_u
        opt_processData.t_dil = solution.time_dil
        opt_processData.time = solution.time

        if optProb.algorithm == "SCVX":
            opt_processData.time_cvx_solver = solution.time_cvx_solver

        if optProb.robot.nrMotors == 2:
            prob_name += "_2m"
        elif optProb.robot.nrMotors == 3:
            prob_name += "_3m"
        elif optProb.robot.nrMotors == 4:
            prob_name += "_4m"
        elif optProb.robot.nrMotors == 6:
            prob_name += "_6m"
        else:
            prob_name += "_8m"

        # save data
        path = "data/"

        filename = path + prob_name

        if optProb.algorithm == "SCVX":
            if alg_pars is not None:
                filename += "_lam_" + str(alg_pars.lam).replace(".","_")
                filename += "_bet_" + str(alg_pars.bet).replace(".","_")
            save_object(filename + "_SCVX", opt_processData)
        elif optProb.algorithm == "KOMO":
            if alg_pars is not None:
                filename += "_wd_" + str(alg_pars.weight_dynamics).replace(".","_")
                filename += "_wi_" + str(alg_pars.weight_input).replace(".","_")
            print(filename + "_KOMO")
            save_object(filename + "_KOMO", opt_processData)

        elif optProb.algorithm == "CASADI":
            save_object(filename + "_CASADI", opt_processData)


def load_object(filename):
    with open(filename, "rb") as input_file:
        sol = pickle.load(input_file)
    return sol

def load_opt_output(prob_name, nrMotors, solver_name, alg_pars = None):

    path = "data/"

    filename = prob_name + "_{}m".format(nrMotors)

    if alg_pars is not None:
        if solver_name == "KOMO":
            filename += "_wd_" + str(alg_pars.weight_dynamics)
            filename += "_wi_" + str(alg_pars.weight_input)
        if solver_name == "SCVX":
            filename += "_lam_" + str(alg_pars.lam)
            filename += "_bet_" + str(alg_pars.bet)

    filename += "_" + solver_name
    
    solution = load_object(path + filename)
        
    return solution

def gen_yaml_files(init_x,init_u,obs,x0,xf,robot):
    init_x = init_x.tolist()
    init_u = init_u.tolist()[:-1]
    dat = {"result": [{'states': init_x,
                      'actions': init_u}]}

    with open("../scripts/temp/guess.yaml", mode="wt", encoding="utf-8") as file:
        yaml.dump(dat, file, default_flow_style=None, sort_keys=False)

    x0 = x0.tolist()
    xf = xf.tolist()
    # to match robot type in croco repo
    r_type = "quadrotor_0"
    min_x = robot.min_x[:3].tolist()
    max_x = robot.max_x[:3].tolist()

    o_l = []
    for o in obs:
        o_l.append({'type': o.type, 'center': o.pos, 'size': o.shape})

    env = {'environment': {'min' : min_x, 'max': max_x, 'obstacles': o_l}}
    rob = {'robots': [{'type': r_type, 'start': x0,'goal': xf}]}

    with open("../scripts/temp/env.yaml", mode="wt", encoding="utf-8") as file:
        yaml.dump(env, file, default_flow_style=None, sort_keys=False)
        yaml.dump(rob, file, default_flow_style=None, sort_keys=False)


def calc_initial_guess(robot, timesteps, noise_factor, xf, x0, intermediate_points, tf_min, tf_max):

    T = timesteps

    # calculate ranges
    state_range = robot.max_x - robot.min_x
    input_range = robot.max_u - robot.min_u

    stateDim = state_range.shape[0]
    actionDim = input_range.shape[0]

    # set up initial trajectory
    initial_x = np.zeros((T, stateDim))
    initial_u = np.zeros((T, actionDim))
    # initial time dilation
    initial_p = (tf_min + tf_max) / 2

    if intermediate_points is not None:
        # sort intermedtiate states in ascending order
        intermediate_points.sort(key=lambda x: x.timing)
        # collect all points that should be visited
        intermediate_positions = [x.value[0:3] for x in intermediate_points if "pos" in x.type]
        # collect timing for positions
        intermediate_pos_timing = [x.timing for x in intermediate_points if "pos" in x.type]
        # collect all orientations that should be visited
        intermediate_quaternions = [x.value[6:10] for x in intermediate_points if "quat" in x.type]
        # collect timing for quaternions
        intermediate_quat_timing = [x.timing for x in intermediate_points if "quat" in x.type]
    else:
        intermediate_positions = []
        intermediate_pos_timing = []
        intermediate_quaternions = []
        intermediate_quat_timing = []

    positions_fixed = [x0[0:3]]
    positions_fixed.extend(intermediate_positions)
    positions_fixed.append(xf[0:3])

    position_timing = [0]
    position_timing.extend(intermediate_pos_timing)
    position_timing.append(T)

    quaternions_fixed = [x0[6:10]]
    quaternions_fixed.extend(intermediate_quaternions)
    quaternions_fixed.append(xf[6:10])

    quaternion_timing = [0]
    quaternion_timing.extend(intermediate_quat_timing)
    quaternion_timing.append(T)

    def calc_interpolation(pos_to_visit, pos_timing, quat_to_visit, quat_timing):
        positions = []
        for i in range(len(pos_to_visit)-1):
            x_s = pos_to_visit[i]
            x_f = pos_to_visit[i+1]
            pos_interp = np.linspace(x_s[0:3], x_f[0:3], pos_timing[i+1] - pos_timing[i])
            positions.append(pos_interp)

        positions = np.concatenate(positions)

        quaternions = []

        for i in range(len(quat_to_visit)-1):
            q_s = rowan.normalize(quat_to_visit[i])
            q_f = rowan.normalize(quat_to_visit[i+1])
            quat_interp = rowan.interpolate.slerp(q_s, q_f, np.linspace(0, 1, quat_timing[i+1] - quat_timing[i]))
            quaternions.append(quat_interp)

        quaternions = np.concatenate(quaternions)

        return positions, quaternions

    ## use interpolation between start and end point as initial guess
    # interpolate positions and quaternions
    interpolated_positions, interpolated_quaternions = calc_interpolation(positions_fixed, position_timing, quaternions_fixed, quaternion_timing)
    initial_x[:, 0:3] += interpolated_positions
    initial_x[:, 6:10] += interpolated_quaternions

    # add gravity compensation
    initial_u[:, :] += (9.81 * robot.mass) / robot.nrMotors

    ## add noise depending on the state and input range
    # pos and vel
    initial_x[1:-1, :6] += np.random.normal(0, state_range[:6] * noise_factor, initial_x[:, :6].shape)[1:-1]

    # orientation
    orient_noise_euler = np.random.normal(0, 2*np.pi * noise_factor, (T,3))
    orient_noise_quat = rowan.from_euler(orient_noise_euler[:,0], orient_noise_euler[:,1], orient_noise_euler[:,2])
    initial_x[1:-1, 6:10] += orient_noise_quat[1:-1]

    # normalize quaternions
    Q = initial_x[:, 6:10]
    Q_norm = np.linalg.norm(initial_x[:, 6:10], axis=1)
    initial_x[:, 6:10] = (Q.T / Q_norm).T

    # rotational velocities
    initial_x[1:-1, 10:] += np.random.normal(0, state_range[10:] * noise_factor, initial_x[:, 10:].shape)[1:-1]

    # input
    initial_u += np.random.normal(0., input_range * noise_factor, initial_u.shape)

    # time dilation
    initial_p += np.random.normal(initial_p, noise_factor, 1)

    return initial_x, initial_u, initial_p

def vis_search_result(s_r,solver_name):
    par_1 = []
    par_2 = []
    costs = []
    times = []
    success = []
    for r in s_r:
        print(" ")
        print("#########################")
        if solver_name == "KOMO":
            print("w_d: {}, w_i: {}".format(r["w_d"], r["w_i"]))
            par_1.append(r["w_d"])
            par_2.append(r["w_i"])
        elif solver_name == "SCVX":
            print("lam: {}, bet: {}".format(r["lam"], r["bet"]))
            par_1.append(r["lam"])
            par_2.append(r["bet"])
        print("cost: {}".format(r["cost"][0]))
        costs.append(r["cost"][0])
        print("success: {}".format(r["check"][0]))
        success.append(r["check"][0])
        print("solver time: {}".format(r["time"][0]))
        times.append(r["time"][0])
        #print("#########################")
    
    plt.rcParams.update({
  		"text.usetex": False,
		})

    fig, axs = plt.subplots(1, 2)

    p1 = axs[0].scatter(par_1, par_2, c = costs, marker="o", cmap="autumn")    
    p2 = axs[1].scatter(par_1, par_2, c = times, marker="o", cmap="autumn")    

    for i in range(len(par_1)):
        print(success[i])
        if not success[i]:
            axs[1].scatter(par_1[i], par_2[i], c = "k", marker ="x")
            axs[0].scatter(par_1[i], par_2[i], c = "k", marker ="x")

    if solver_name == "KOMO":
        axs[0].set_xlabel("w_d")
        axs[0].set_ylabel("w_i")
        axs[1].set_xlabel("w_d")
        axs[1].set_ylabel("w_i")
    elif solver_name == "SCVX":
        axs[0].set_xlabel("lam")
        axs[0].set_ylabel("bet")
        axs[1].set_xlabel("lam")
        axs[1].set_ylabel("bet")

    axs[0].set_title("costs")
    axs[1].set_title("time")

    plt.colorbar(p1, ax=axs[0])
    plt.colorbar(p2, ax=axs[1])

    fig.savefig("plots/parameter_search.pdf")