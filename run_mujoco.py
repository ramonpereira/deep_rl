import os
import gym
import time
import argparse
import datetime
import numpy as np
import torch
from torch.utils.tensorboard import SummaryWriter

# Configurations
parser = argparse.ArgumentParser(description='RL algorithms with PyTorch in MuJoCo environments')
parser.add_argument('--env', type=str, default='Humanoid-v2', 
                    help='choose an environment between HalfCheetah-v2, Ant-v2 and Humanoid-v2')
parser.add_argument('--algo', type=str, default='atac', 
                    help='select an algorithm among vpg, npg, trpo, ppo, ddpg, td3, sac, asac, tac, atac')
parser.add_argument('--seed', type=int, default=0, 
                    help='seed for random number generators')
parser.add_argument('--iterations', type=int, default=200, 
                    help='iterations to run and train agent')
parser.add_argument('--steps_per_iter', type=int, default=5000, 
                    help='steps of interaction for the agent and the environment in each epoch')
parser.add_argument('--max_step', type=int, default=1000,
                    help='max episode step')
parser.add_argument('--tensorboard', type=bool, default=True)
parser.add_argument('--gpu_index', type=int, default=0)
args = parser.parse_args()
device = torch.device('cuda', index=args.gpu_index) if torch.cuda.is_available() else torch.device('cpu')

if args.algo == 'vpg':
    from agents.vpg import Agent
elif args.algo == 'npg':
    from agents.trpo import Agent
elif args.algo == 'trpo':
    from agents.trpo import Agent
elif args.algo == 'ppo':
    from agents.ppo import Agent
elif args.algo == 'ddpg':
    from agents.ddpg import Agent
elif args.algo == 'td3':
    from agents.td3 import Agent
elif args.algo == 'sac':
    from agents.sac import Agent
elif args.algo == 'asac': # Automating entropy adjustment on SAC
    from agents.sac import Agent
elif args.algo == 'tac': 
    from agents.sac import Agent
elif args.algo == 'atac': # Automating entropy adjustment on TAC
    from agents.sac import Agent


def main():
    """Main."""
    # Initialize environment
    env = gym.make(args.env)
    obs_dim = env.observation_space.shape[0]
    act_dim = env.action_space.shape[0]
    act_limit = env.action_space.high[0]
    print('State dimension:', obs_dim)
    print('Action dimension:', act_dim)

    # Set a random seed
    env.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    # Create an agent
    if args.algo == 'ddpg' or args.algo == 'td3':
        agent = Agent(env, args, device, obs_dim, act_dim, act_limit, 
                      start_steps=10000, 
                      act_noise=0.1, 
                      hidden_sizes=(256,256), 
                      buffer_size=int(1e6), 
                      batch_size=256,
                      policy_lr=1e-4, 
                      qf_lr=1e-3)
    elif args.algo == 'sac':                                                                                    
        agent = Agent(env, args, device, obs_dim, act_dim, act_limit,                   
                      start_steps=10000,                                
                      alpha=0.05,                       # In HalfCheetah-v2 and Ant-v2, SAC with 0.2  
                      hidden_sizes=(256,256),           # shows the best performance in entropy coefficient 
                      buffer_size=int(1e6),             # while, in Humanoid-v2, SAC with 0.05 shows the best performance.
                      batch_size=256,
                      policy_lr=3e-4, 
                      qf_lr=3e-4)     
    elif args.algo == 'asac':
        agent = Agent(env, args, device, obs_dim, act_dim, act_limit, 
                      start_steps=10000, 
                      automatic_entropy_tuning=True, 
                      hidden_sizes=(256,256), 
                      buffer_size=int(1e6), 
                      batch_size=256,
                      policy_lr=3e-4,
                      qf_lr=3e-4)
    elif args.algo == 'tac':                                                                                    
        agent = Agent(env, args, device, obs_dim, act_dim, act_limit,                   
                      start_steps=10000,                                
                      alpha=0.05,                                       
                      log_type='log-q',                 # In HalfCheetah-v2 and Ant-v2, TAC with 1.5  
                      entropic_index=1.2,               # shows the best performance in entropic index 
                      hidden_sizes=(256,256),           # while, in Humanoid-v2, TAC with 1.2 shows the best performance.
                      buffer_size=int(1e6), 
                      batch_size=256,
                      policy_lr=3e-4,
                      qf_lr=3e-4)
    elif args.algo == 'atac':
        agent = Agent(env, args, device, obs_dim, act_dim, act_limit, 
                      start_steps=10000, 
                      log_type='log-q', 
                      entropic_index=1.2, 
                      automatic_entropy_tuning=True,
                      hidden_sizes=(256,256), 
                      buffer_size=int(1e6), 
                      batch_size=256,
                      policy_lr=3e-4,
                      qf_lr=3e-4)
    else: # vpg, npg, trpo, ppo
        agent = Agent(env, args, device, obs_dim, act_dim, act_limit, sample_size=4000)

    # Create a SummaryWriter object by TensorBoard
    if args.tensorboard:
        dir_name = 'runs/' + args.env + '/' + args.algo + '/' + str(args.seed) \
                    + '_' + datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        writer = SummaryWriter(log_dir=dir_name)

    start_time = time.time()

    total_num_steps = 0
    train_sum_returns = 0.
    train_num_episodes = 0

    # Main loop
    for i in range(args.iterations):
        train_step_count = 0
        while train_step_count <= args.steps_per_iter:
            # Perform the training phase, during which the agent learns
            agent.eval_mode = False
            
            # Run one episode
            train_step_length, train_episode_return = agent.run(args.max_step)
            
            total_num_steps += train_step_length
            train_step_count += train_step_length
            train_sum_returns += train_episode_return
            train_num_episodes += 1

            train_average_return = train_sum_returns / train_num_episodes if train_num_episodes > 0 else 0.0

            # Log experiment result for training steps
            if args.tensorboard:
                writer.add_scalar('Train/AverageReturns', train_average_return, total_num_steps)
                writer.add_scalar('Train/EpisodeReturns', train_episode_return, total_num_steps)
                if args.algo == 'asac' or args.algo == 'atac':
                    writer.add_scalar('Train/Alpha', agent.alpha, total_num_steps)

        # Perform the evaluation phase -- no learning
        agent.eval_mode = True
        
        eval_sum_returns = 0.
        eval_num_episodes = 0

        for _ in range(10):
            # Run one episode
            eval_step_length, eval_episode_return = agent.run(args.max_step)

            eval_sum_returns += eval_episode_return
            eval_num_episodes += 1

        eval_average_return = eval_sum_returns / eval_num_episodes if eval_num_episodes > 0 else 0.0

        # Log experiment result for evaluation steps
        if args.tensorboard:
            writer.add_scalar('Eval/AverageReturns', eval_average_return, total_num_steps)
            writer.add_scalar('Eval/EpisodeReturns', eval_episode_return, total_num_steps)

        print('---------------------------------------')
        print('Iterations:', i)
        print('Steps:', total_num_steps)
        print('Episodes:', train_num_episodes)
        print('AverageReturn:', round(train_average_return, 2))
        print('EvalEpisodes:', eval_num_episodes)
        print('EvalAverageReturn:', round(eval_average_return, 2))
        print('OtherLogs:', agent.logger)
        print('Time:', int(time.time() - start_time))
        print('---------------------------------------')

        # Save the trained model
        if (i + 1) % 20 == 0:
            if not os.path.exists('./tests/save_model'):
                os.mkdir('./tests/save_model')
            
            ckpt_path = os.path.join('./tests/save_model/' + args.env + '_' + args.algo \
                                                                            + '_s_' + str(args.seed) \
                                                                            + '_i_' + str(i) \
                                                                            + '_st_' + str(total_num_steps) \
                                                                            + '_tr_' + str(round(train_average_return, 2)) \
                                                                            + '_er_' + str(round(eval_average_return, 2)) + '.pt')
            
            torch.save(agent.policy.state_dict(), ckpt_path)

if __name__ == "__main__":
    main()
