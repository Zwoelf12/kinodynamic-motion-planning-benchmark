from optimization.parallelization import Multiprocess, build_arg_combinations
from compare_komo_scp_casadi import run_optimization, visualize_optimization
from optimization.problem_setups import Prob_setup
from optimization.algorithm_parameters import KOMO_parameter,SCVX_parameter,CASADI_parameter
from optimization import opt_utils as ou

list_of_solvers = ["KOMO"]
search = True

# choose which problem should be solved
prob = 4
prob_setup = Prob_setup(prob)
prob_name = prob_setup.name

filename = "data/parameter_search/" + prob_name + "_4m_KOMO"

if search:
    # KOMO: iterate over different weight_dynamics, weight_inputs 

    all_weight_dynamic = [1e0, 1e0*3, 1e0*7, 1e1, 1e1*3, 1e1*5]# [1e0, 1e0*3, 1e0*7, 1e1, 1e1*3, 1e1*5] #[1e1*0.8, 1e1*0.9, 1e1, 1e1*2, 1e1*3, 1e1*4, 1e1*5]  #[1e0, 1e1, 1e2,1e3,1e4,1e5]
    all_weight_input = [1e3*0.9, 1e3, 1e3*2, 1e3*3, 1e3*4] #[1e3*0.9, 1e3, 1e3*2, 1e3*3, 1e3*4] #[1e3*2, 1e3*3, 1e3*4, 1e3*5, 1e3*6, 1e3*7, 1e3*8]  #[1e0, 1e1, 1e2,1e3,1e4,1e5]
    all_args_KOMO = build_arg_combinations([all_weight_dynamic,all_weight_input], 1, "all")

    # build list of all parameters for run optimization function
    all_alg_pars = []
    all_prob_names = []
    all_prob_setups = []
    all_lists_of_solvers = []
    all_parameter_search = []
    for w in all_args_KOMO:
        par_KOMO = KOMO_parameter(prob_name)
        par_KOMO.weight_dynamics = w[0]
        par_KOMO.weight_input = w[1]

        all_alg_pars.append({"KOMO":par_KOMO,
                            "SCVX":SCVX_parameter(prob_name),
                            "CASADI":CASADI_parameter(prob_name)})
        
        all_prob_names.append(prob_name)
        all_prob_setups.append(prob_setup)
        all_lists_of_solvers.append(list_of_solvers)
        all_parameter_search.append(True)

    # put all arg in one list (order is important)
    args = [all_prob_names, all_prob_setups, all_lists_of_solvers, all_alg_pars, all_parameter_search]    

    process_handler = Multiprocess(run_optimization, args)
    results = process_handler.run_processes()

    search_result = []
    for r,a_p in zip(results,all_alg_pars):
        r["w_i"] = a_p["KOMO"].weight_input
        r["w_d"] = a_p["KOMO"].weight_dynamics
        search_result.append(r)

    ou.save_object(filename, search_result)

search_result = ou.load_object(filename)

ou.vis_search_result(search_result, "KOMO")

"""
solutions = {}
for solver_name in list_of_solvers:
    sol_now = ou.load_opt_output(prob_name, 4, solver_name)
    solutions[solver_name] = sol_now
"""