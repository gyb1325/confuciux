'''
Working version for both GEMM and nonGEMM
'''
import random
import os, sys
import argparse
import torch
from collections import deque
import matplotlib.pyplot as plt
script_dir = os.path.dirname(__file__)
module_path = os.path.abspath(os.path.join(script_dir, '../../'))
if module_path not in sys.path:
    sys.path.insert(0,module_path)
import src.ConfX.ga_confx as ga
from src.ConfX.env_confx import MaestroEnvironment
import pickle
from src.ConfX.rl_confx import Agent
import pandas as pd
import copy
from datetime import datetime
from src.utils.hw_spec_get import *
from src.utils.utils import *
import glob
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")



def policy_graident(n_episodes=100000, max_t=1000, print_every=10, outfile="out.plt", chkpt_file="trial.plt", eps=0,temperature=1):

    best_score = -2**20
    scores_window = deque(maxlen=print_every)
    scores = []
    episodes = 0
    has_succeed_history = False
    for i_episode in range(1 + episodes, n_episodes + episodes + 1):
        if (i_episode+1) %100 ==0  and has_succeed_history:
            eps /= 1.2
            temperature /=1.01
            temperature = max(temperature,1)
            agent.ajust_lr(ratio=0.8, min_lr=1e-6)

        score = 0
        env.shuffle_model()
        state, infos = env.reset()
        for t in range(max_t):
            action, log_prob = agent.act(state, infos, eps,temperature)
            next_state, reward, done, infos, sig, impt= env.step(action)
            agent.step(state, action, log_prob, reward, next_state, done, sig, impt, infos)
            state = next_state
            score += reward
            if done:
                break
        scores_window.append(score)
        scores.append(score)
        if np.mean(scores_window) > best_score:
            best_score = np.mean(scores_window)
        agent_chkpt = agent.get_chkpt()
        env_chkpt = env.get_chkpt()
        others_chkpt =  {
                 "scores": scores,
                 "best_score": best_score,
                 "scores_window":scores_window,
                 "episodes":i_episode}
        chkpt = {"agent_chkpt": agent_chkpt,
                 "env_chkpt": env_chkpt,
                 "others_chkpt": others_chkpt}
        if i_episode % 5 == 0:
            env.save_chkpt(chkpt_file)
            torch.save(chkpt, outfile)

        if infos["succeed"]:
            has_succeed_history = True
            print("Episode {}: succeed".format(i_episode))
        else:
            print("Episode {}: finding".format(i_episode))




    return scores

def get_probe_int(sol):
    sol = np.array(sol)
    sol = sol.flatten()
    parms = {"{}".format(i): e for i, e in enumerate(sol)}
    return parms

def get_probe(sol):
    sol = np.log2(sol)
    sol = sol.flatten()
    parms = {"{}".format(i): e for i, e in enumerate(sol)}
    return parms


def genetic_search(best_sol, best_reward, action_bound, action_bottom, num_layers=None, num_generations=100, num_pop = 20):
    reward_record_g = []
    best_rewards_g = []
    best_sol_g = best_sol
    best_reward_g = best_reward
    num_layers = num_layers if num_layers else len(model_defs)


    num_generations = num_generations
    num_population = num_pop
    num_parents_init = 8

    new_population = np.ones((num_population, num_layers, 2)) * best_sol

    count = 0

    fitness = np.ones((num_population, 2), float) * best_reward

    print("Cases {}: reward: {}".format(0, best_reward_g))
    count_non_valid = 0
    for g in range(num_generations):
        gen_best = -float("Inf")
        num_parents = min(num_parents_init, num_population - count_non_valid)
        count_non_valid = 0

        parents = ga.select_parents(new_population, fitness,
                                    num_parents, num_layers)


        ga.mutation(parents, new_population, action_bound, action_bottom, env, fitness, range_alpha=ratio)
        ga.self_crossover(new_population, eps=0.2)
        new_population[0, :] = parents[0]

        for i in range(num_population):
            reward, total_constraint = env.exterior_search(new_population[i])
            if total_constraint > env.constraint_value:
                reward = float("-Inf")
                count_non_valid += 1
            gen_best = max(gen_best, reward)
            fitness[i] = np.array([reward, total_constraint])
        max_idx = np.argmax(fitness[:, 0])
        reward_record_g.append(copy.deepcopy(np.nanmean(fitness[fitness[:, 0] > float("-Inf")], axis=0)))
        if best_reward_g[0] < fitness[max_idx][0]:
            best_reward_g = copy.deepcopy(fitness[max_idx])
            best_sol_g = copy.deepcopy(new_population[max_idx])
        best_rewards_g.append(best_reward_g)
        chkpt = {
            "best_sol_g": best_sol_g,
            "best_rewards_g": best_rewards_g,
            "reward_record_g": reward_record_g,
            "num_population_g": num_population,
            "num_generations_g": num_generations,
            "num_parents_g": num_parents
        }

        print("Gen {}: Gen reward: {}, Best reward: {}".format((g + 1) , gen_best,
                                                                               best_reward_g))

    return chkpt


def check_sol(sol):
    reward = env.exterior_search(sol)
    print("Reward: {}".format(reward))
    return reward

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--outdir', type=str, default="outdir", help='output directiory')
    parser.add_argument('--model_def', type=str, default="vgg16", help='The experimenting model.')
    parser.add_argument('--fitness', type=str, default="latency", help='The objective.')
    parser.add_argument('--cstr', type=str, default="area", help='The constraint.')
    parser.add_argument('--platform', type=str, default="cloud", help='[Cloud, IoT, eIoT].')
    parser.add_argument('--epochs', type=int, default=100, help='pickle file name')
    parser.add_argument('--gpu', default=0, type=int, help='which gpu')
    parser.add_argument('--df', default="shi", type=str, help='The dataflow strategy.')
    opt = parser.parse_args()
    ratio = get_platform_ratio(opt.platform)
    device = 'cuda:' + str(opt.gpu) if torch.cuda.is_available() else 'cpu'
    

    epoch_rl, epoch_ga = opt.epochs* 2//3, opt.epochs//3,
    now = datetime.now()
    now_date = "{}".format(now.date())
    now_time = "{}".format(now.time())
    is_discrete = True
    n_acts = 2
    dis_or_cont = "D" if is_discrete else "C"
    alg = "REINFORCE"
    outdir = opt.outdir
    outdir = os.path.join("../../", outdir)
    exp_name = "{}_F-{}_C-{}_Plt-{}_DF-{}_{}_{}".format(opt.model_def, opt.fitness, opt.cstr, opt.platform, opt.df, alg,
                                                dis_or_cont)

    outdir_exp = os.path.join(outdir, exp_name)
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(outdir_exp, exist_ok=True)
    chkpt_file_t =  os.path.join(outdir_exp,"{}".format("result"))



    outfile = chkpt_file_t + "_o.plt"
    chkpt_file =  chkpt_file_t + "_c.plt"
    img_file = chkpt_file_t + ".png"
    log_file = chkpt_file_t + ".csv"



    action_space, action_bound, action_bottom = get_action_space()
    m_file_path = "../../data/modelfile/"
    m_file = os.path.join(m_file_path, opt.model_def + "_m.csv")
    df = pd.read_csv(m_file,header=None)
    model_defs = df.to_numpy()
    _,dim_size = model_defs.shape


    try:
        # ============================Start Env============================================================================================

        agent = Agent(dim_size=dim_size, resource_size=2, n_action_steps = 2, action_size=12, seed=random.randint(0, 2**63))

        env = MaestroEnvironment(model_defs=model_defs,dim_size=dim_size, resource_size=2,n_action_steps=2, dataflow=opt.df)
        state = env.reset()
        env.set_fitness(opt.fitness)
        env.set_constraint(opt.cstr)
        constraint_temp = [env.get_ref_constraint([action_bound[0], action_bound[1]]),
                           env.get_ref_constraint([action_bottom[0], action_bottom[1]]),
                           env.get_ref_constraint([action_bound[0], action_bottom[1]]),
                           env.get_ref_constraint([action_bottom[0], action_bound[1]])]
        max_constraint, min_constraint = max(constraint_temp), min(constraint_temp)
        print("Max constraint: {}".format(max_constraint))
        print("Min constraint: {}".format(min_constraint))
        set_constraint = min_constraint + (max_constraint - min_constraint) * ratio

        env.set_constraint_value(max_constraint, min_constraint, set_constraint)
        print("Set constraint: {}".format(set_constraint))
        # ========================================================================================================================



        # ============================Do training============================================================================================
        agent.set_fitness(opt.fitness)
        agent.reset()
        # env.shuffle_model()
        scores = policy_graident(n_episodes=epoch_rl,  outfile=outfile, chkpt_file=chkpt_file, eps=0.0, temperature=1)
        #========================================================================================================================


        # ============================Open save file============================================================================================
        length = -1
        with open(chkpt_file, "rb") as fd:
            chkpt = pickle.load(fd)

        best_rewards = chkpt["best_rewards"][:length]
        reward_rec = chkpt["reward_rec"][:length]
        best_sol = chkpt["best_sol"]["sol"]
        best_sol_ctr = chkpt["best_sol"]["ctr"]
        sols = chkpt["sols"]
        sol_reward_record = chkpt["sol_reward_record"]
        set_constraint = chkpt["ctrs_info"]["value"]
        max_constraint = chkpt["ctrs_info"]["max"]
        min_constraint = chkpt["ctrs_info"]["min"]
        reward, constraint = env.exterior_search(best_sol)
        print("Reward: ", reward)
        print("Constraint: ", constraint)

        #========================================================================================================================



        # ============================Do Genetic============================================================================================

        chkpt_g = genetic_search(best_sol, (best_rewards[-1],best_sol_ctr), action_bound, action_bottom,num_generations=epoch_ga,num_layers=len(best_sol))
        chkpt.update(chkpt_g)
        with open(chkpt_file, "wb") as fd:
            pickle.dump(chkpt, fd)
        chkpt_g = chkpt
        # ========================================================================================================================



        # ==========================Do plotting ======================================================================================

        best_sol_g = chkpt_g["best_sol_g"]
        sbest_rewards_g = chkpt_g["best_rewards_g"]
        sreward_record_g = chkpt_g["reward_record_g"]
        reward_rec_g = [r for r, c in sreward_record_g]
        best_rewards_g = [r for r, c in sbest_rewards_g]
        best_rewards_c = [c for r, c in sbest_rewards_g]
        best_sol_ctr = best_rewards_c[-1]

        best_sol = np.vstack(best_sol_g).astype(int)
        # best_sol = [a  for A in best_sol for a in A]
        reward_rec = reward_rec + reward_rec_g
        best_rewards = best_rewards + best_rewards_g
        best_reward_point = abs(best_rewards[-1])
        default_min = float("-inf")

        # idx = bisect.bisect_right(best_rewards, default_min)
        # best_rewards[:idx] = [best_rewards[idx] - 1 for _ in range(idx)]
        # print("Start to valid at {} epoch".format(idx))
        print("Best  fitness :{:9e}".format(best_reward_point))
        print("Sol:\n {}\n".format(best_sol))
        print("Used constraint: {}".format(best_sol_ctr))
        print("Set constraint: {} [Constraint range : ({}, {})]".format(set_constraint, min_constraint, max_constraint))
        with open(log_file, "a") as fd:
            fd.write("\n" + "=" * 10 + "ConfuciuX" + "=" * 10 + "\n")
            fd.write("best rewards: {}\n".format(best_reward_point))
            fd.write("best sol:\n {}\n".format(best_sol))
            fd.write("Used constraint: {}\n".format(best_sol_ctr))
            fd.write(
                "Set constraint: {} [Constraint range : ({}, {})]\n".format(set_constraint, min_constraint, max_constraint))
            fd.write("Model: {}\n".format(opt.model_def))
            fd.write("{}".format(model_defs))

        #
        font = {
            'weight': 'bold',
            'size': 12}
        import matplotlib

        matplotlib.rc('font', **font)
        fig = plt.figure(0, figsize=(6, 3))
        ax = fig.add_subplot(111)
        plt.plot(np.arange(len(best_rewards)), np.abs(np.array(best_rewards)), label="ConX", linewidth=5)
        plt.yscale("log")
        plt.legend()
        fig.tight_layout()
        plt.savefig(img_file, dpi=300)
        plt.show()

    finally:
        for f in glob.glob("*.m"):
            os.remove(f)
        for f in glob.glob("*.csv"):
            os.remove(f)