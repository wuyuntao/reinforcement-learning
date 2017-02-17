#!/usr/bin/python
# -*- coding: utf-8 -*-

from datetime import datetime
import gym
from gym import wrappers
import numpy as np
import random
import tensorflow as tf

tf.app.flags.DEFINE_integer('training_episodes', 10)
tf.app.flags.DEFINE_boolean('enable_env_monitor', False)
tf.app.flags.DEFINE_integer('minibatch_size', 32)
tf.app.flags.DEFINE_integer('replay_memory_capacity', 1000000)
tf.app.flags.DEFINE_integer('target_network_update_freq', 10000)
tf.app.flags.DEFINE_float('discount_factor', 0.99)
tf.app.flags.DEFINE_float('learning_rate', 0.00025)
tf.app.flags.DEFINE_float('gradient_momentum', 0.95)
tf.app.flags.DEFINE_float('initial_exploration', 1)
tf.app.flags.DEFINE_float('final_exploration', 0.1)
tf.app.flags.DEFINE_integer('final_exploration_frame', 1000000)

FLAGS = tf.app.flags.FLAGS


def get_exploration_rate(step):
    return np.interp(step,
                     (0, FLAGS.final_exploration_frame),
                     (FLAGS.initial_exploration, FLAGS.final_exploration))


class ReplayMemory(object):
    """Replay memory"""
    def __init__(self, capacity):
        self._capacity = capacity
        self._steps = []

    def add(self, observation, action, next_observation, reward, done):
        step = ReplayStep(observation, action, next_observation, reward, done)
        self._steps.append(step)

        while len(self._steps) > self._capacity:
            self._steps.pop(0)

    def get_batch(self, minibatch_size):
        return random.sample(self._steps, minibatch_size)


class ReplayStep(object):
    """Replay step"""
    def __init__(self, observation, action, next_observation, reward, done):
        self.observation = observation
        self.action = action
        self.next_observation = next_observation
        self.reward = reward
        self.done = done


class DQN(object):
    """Deep Q-Network implemented via TensorFlow"""
    def __init__(self, env, session):
        self._env = env
        self._session = session

        with tf.variable_scope('input0'):
            self._input0 = tf.placeholder(
                tf.float32, [-1, 84, 84, 3], name="input_layer")

        with tf.variable_scope('conv1'):
            self._conv1 = tf.contrib.layers.conv2d(
                self._inputs, 32,
                kernel_size=[8, 8], stride=[4, 4], padding="VALID",
                activation_fn=tf.nn.relu, name="conv_layer_1")

        with tf.variable_scope('conv2'):
            self._conv2 = tf.contrib.layers.conv2d(
                self._conv1, 64,
                kernel_size=[4, 4], stride=[2, 2], padding="VALID",
                activation_fn=tf.nn.relu, name="conv_layer_2")

        with tf.variable_scope('conv3'):
            self._conv3 = tf.contrib.layers.conv2d(
                self._conv2, 64,
                kernel_size=[3, 3], stride=[1, 1], padding="VALID",
                activation_fn=tf.nn.relu, name="conv_layer_3")
            self._conv3_flat = tf.reshape(self._conv3, [-1, 3 * 3 * 64])

        with tf.variable_scope('dense4'):
            self._dense4 = tf.contrib.layers.fully_connected(
                self._conv3_flat, 512,
                activation_fn=tf.nn.relu, name="dense_layer_4")

        with tf.variable_scope('dense5'):
            self._dense5 = tf.contrib.layers.fully_connected(
                self._dense4, 512,
                activation_fn=tf.nn.relu, name="dense_layer_5")

        with tf.variable_scope('output6'):
            self._q = tf.contrib.layers.fully_connected(
                self._dense5, self._env.action_space.n,
                activation_fn=tf.nn.sigmoid, name="q_output")
            self._q_action = tf.argmax(self._q, 1, name="q_action")
            self._q_max = tf.reduce_max(self._q, name="q_max")

        with tf.variable_scope('target'):
            self._q_target = tf.placeholder(
                tf.float32, [1, self._env.action_space.n],
                name="q_target")
            self._loss = tf.reduce_sum(tf.square(self._q_target - self._q))

        with tf.variable_scope('optimizer'):
            self._optimizer = tf.train.RMSPropOptimizer(
                learning_rate=FLAGS.learning_rate,
                decay=FLAGS.discount_factor,
                momentum=FLAGS.gradient_momentum,
                epsilon=0.01).minimize(self._loss)

    def get_best_action(self, observation):
        action = self._session.run([self._q_action], {
            self._input0: self._preprocess_observation(observation)
        })
        return action[0]

    def train(self, batches):
        for step in batches:
            q = step.reward
            if not step.done:
                next_q_max = self._session.run(self._q_max, {
                    self._input0: self._preprocess_observation(
                        step.next_observation)
                    })
                q += FLAGS.discount_factor * next_q_max
            q_target = np.zeros(self._env.action_space.n, np.float32)
            q_target[step.action] = q

            self._session.run(self._optimizer, {
                self._input0: self._preprocess_observation(
                    step.observation),
                self._q_target: q_target,
            })

    def update_target_params(self):
        pass

    def _preprocess_observation(self, observation):
        return observation


def main(_):
    # Initialize tensorflow session
    session = tf.Session()
    # Initialize gym enviroment
    env = gym.make('CartPole-v0')
    if FLAGS.enable_env_monitor:
        timestamp = datetime.strftime(datetime.now(), '%Y%m%d%H%M%S')
        replay_name = 'data/cartpole-v0-experiment-{}'.format(timestamp)
        env = wrappers.Monitor(env, replay_name)
    # Initialize replay memory
    memory = ReplayMemory(FLAGS.replay_memory_capacity)
    # Initialize action-value function Q
    q = DQN(session)
    train_step = 1
    # For episode = 1, M do
    for epoch in range(FLAGS.training_episodes):
        # Initialize sequence s1
        observation = env.reset()
        done = False
        # For t = 1, T
        episode_step = 1
        while not done:
            env.render()
            # With probability epsilon select a random action
            exploration_rate = get_exploration_rate(train_step)
            if random.random() <= exploration_rate:
                action = env.action_space.sample()
            # otherwise select the action with best promise
            else:
                action = q.get_best_action(observation)
            # Execute selected action and observe reward and image
            next_observation, reward, done, info = env.step(action)
            # Store transition in memory
            memory.add(observation, action, next_observation, reward, done)
            # Sample random minibatch of transitions from memory
            minibatch = memory.get_batch(FLAGS.minibatch_size)
            # Perform a SGD step with respect to the network parameter
            q.train(minibatch)
            if train_step % FLAGS.target_network_update_freq == 0:
                q.update_target_params()
            # Print training status
            print('Episode {}, Step {}, Done {}'
                  .format(epoch, episode_step, done))
            observation = next_observation
            episode_step += 1
            train_step += 1
    session.close()


if __name__ == '__main__':
    tf.app.run()
