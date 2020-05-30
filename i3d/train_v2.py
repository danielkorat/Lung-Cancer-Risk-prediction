# ******************************************************************************
# Copyright 2017-2018 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ******************************************************************************
from __future__ import division
from __future__ import print_function
from random import shuffle
import os
import numpy as np
import utils

import argparse
import tensorflow as tf
from i3d import InceptionI3d
from os.path import join

def main(args):
    # Set GPU
    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu_id

    # Create model dir if it doesn't exist
    if not os.path.exists(args.model_dir):
        os.makedirs(args.model_dir)
    model_path = args.model_dir

    # Create train and dev sets
    print("Creating training and validation sets")
    train_list = utils.load_data_list(join(args.data_dir, args.train))
    val_list = utils.load_data_list(join(args.data_dir, args.test))

    model = I3dForCTVolumes(data_dir=args.data_dir, batch_size=args.batch_size, device=args.select_device)

    # Define Configs for training
    run_config = tf.ConfigProto(allow_soft_placement=True, log_device_placement=False)

    # Create session run training
    # with tf.Session(config=run_config) as sess:
    # init = tf.global_variables_initializer()
    # self.sess.run(init)

    # Model Saver
    # model_saver = tf.train.Saver()
    # model_ckpt = tf.train.get_checkpoint_state(model_path)
    # idx_path = model_ckpt.model_checkpoint_path + ".index" if model_ckpt else ""

    # Intitialze with pretrained weights
    print('\nINFO: Loading from previously stored session \n')
    # pretrained_saver.restore(sess, model_ckpt.model_checkpoint_path)
    model.pretrained_saver.restore(model.sess, join(args.data_dir, args.ckpt))
    print('\nINFO: Loaded pretrained model \n')

    if args.inference_mode:
        print('\nINFO: Begin Inference Mode \n')
        # Shuffle Validation Set
        shuffle(dev)
        # Run Inference Mode
        model.inference_mode(sess, dev, [vocab_dict, vocab_rev],
                            num_examples=args.num_examples, dropout=1.0)
    else:
        print('\nINFO: Begin Training \n')

        for epoch in range(args.epochs):
            print("\n+++++++++++++++Epoch Number: ", epoch + 1)

            # Shuffle Dataset
            shuffle(train_list)

            # Run training for 1 epoch
            model.train_loop(train_list, args.batch_size)

            # Save Weights after each epoch
            print("Saving Weights")
            # model_saver.save(sess, "{}/trained_model_{}.ckpt".format(model_path, epoch))

            # Start validation phase at end of each epoch
            print("Begin Validation")
            # run_loop(sess, processed_val, placeholders, mode='val')


class I3dForCTVolumes:
    def __init__(self, data_dir, batch_size, learning_rate=0.0001, device='GPU', num_frames=140, crop_size=224):
        self.data_dir = data_dir
        self.crop_size = crop_size
        self.num_frames = num_frames

        with tf.Graph().as_default():
            # Learning Rate
            global_step = tf.get_variable(
                    'global_step',
                    [],
                    initializer=tf.constant_initializer(0),
                    trainable=False
                    )

            # Placeholders
            self.images_placeholder, self.labels_placeholder, self.is_training_placeholder = utils.placeholder_inputs(
                    batch_size=batch_size,
                    num_frame_per_clip=self.num_frames,
                    crop_size=self.crop_size,
                    rgb_channels=3
                    )

            # self.lr = tf.train.exponential_decay(learning_rate, self.global_step, decay_steps=3000, decay_rate=0.1, staircase=True)
            learning_rate = tf.train.exponential_decay(learning_rate, global_step, decay_steps=3000, decay_rate=0.1, staircase=True)
            opt_rgb = tf.train.AdamOptimizer(learning_rate)

            # Init I3D model
            with tf.device('/device:' + device + ':0'):
                with tf.variable_scope('RGB'):
                    rgb_logit, _ = InceptionI3d(num_classes=2)(self.images_placeholder, self.is_training_placeholder)

                rgb_loss = utils.tower_loss(
                                rgb_logit,
                                self.labels_placeholder
                                )
                accuracy = utils.tower_acc(rgb_logit, self.labels_placeholder)
                update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
                with tf.control_dependencies(update_ops):
                    rgb_grads = opt_rgb.compute_gradients(rgb_loss)
                    apply_gradient_rgb = opt_rgb.apply_gradients(rgb_grads, global_step=global_step)
                    self.train_op = tf.group(apply_gradient_rgb)
                    null_op = tf.no_op()

            self.accuracy = accuracy
            self.loss = rgb_loss

            # Create a saver for loading pretrained checkpoints.
            pretrained_variable_map = {}
            for variable in tf.global_variables():
                if variable.name.split('/')[0] == 'RGB' and 'Adam' not in variable.name.split('/')[-1] and variable.name.split('/')[2] != 'Logits':
                    pretrained_variable_map[variable.name.replace(':0', '')] = variable
            self.pretrained_saver = tf.train.Saver(var_list=pretrained_variable_map, reshape=True)

            init = tf.global_variables_initializer()
            # Create a session for running Ops on the Graph.
            self.sess = tf.Session(config=tf.ConfigProto(allow_soft_placement=True))
            self.sess.run(init)

    def train_loop(self, data_list, batch_size=1):
        for i, list_batch in utils.batch(data_list, batch_size):
            print('============\nStep {}', i)
            images_batch, labels_batch = self.process_coupled_data(list_batch)
            print('batch size: {} ', len(images_batch))
            feed_dict = self.coupled_data_to_dict(images_batch, labels_batch, is_training=True)

            # _, train_loss, _, logits, labels = sess.run(
            #     [self.optimizer, self.loss, self.lr, self.logits, self.labels_placeholder], feed_dict=feed_dict)

            self.sess.run(self.train_op, feed_dict=feed_dict)

            if i % 10 == 0:
                # print('iteration = {}, train loss = {}'.format(i, train_loss))
                # accuracy, auc = calc_metrics(labels, logits)
                # print("train accuracy = {}, train auc = {}", accuracy, auc)
                feed_dict = self.coupled_data_to_dict(images_batch, labels_batch, is_training=False)
                acc, loss = self.sess.run([self.accuracy, self.loss], feed_dict=feed_dict)
                print("accuracy: " + "{:.5f}".format(acc))
                print("rgb_loss: " + "{:.5f}".format(loss))                

            # self.global_step.assign(self.global_step + 1)

    def coupled_data_to_dict(self, train_images, train_labels, is_training):
        return {
                self.images_placeholder: train_images,
                self.labels_placeholder: train_labels,
                self.is_training_placeholder: is_training
                }

    def process_coupled_data(self, coupled_data):
        data = []
        labels = []
        for cur_file, label in coupled_data:
            print("Loading image from {} with label {}".format(cur_file, label))
            result = np.zeros((self.num_frames, self.crop_size, self.crop_size, 3)).astype(np.float32)
            scan_arr = np.load(join(self.data_dir, cur_file)).astype(np.float32)
            result[:self.num_frames, :scan_arr.shape[1], :scan_arr.shape[2], :3] = \
                scan_arr[:self.num_frames, :self.crop_size, :self.crop_size, :3]
            data.append(result)
            labels.append(label)
        np_arr_data = np.array(data)
        np_arr_labels = np.array(labels).astype(np.int64).reshape(len(coupled_data))
        return np_arr_data, np_arr_labels


if __name__ == "__main__":
    # Parse the command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_dir', default='/home/daniel_nlp/Lung-Cancer-Risk-Prediction/i3d/data', help='path to training data')

    parser.add_argument('--train', default='debug_train.list', help='path to training data')

    parser.add_argument('--test', default='debug_test.list', help='path to training data')

    parser.add_argument('--gpu_id', default="0", type=str, help='gpu id')

    parser.add_argument('--epochs', default=2, type=int,  help='the number of epochs')

    parser.add_argument('--select_device', default='GPU', type=str, help='the device to execute on')

    parser.add_argument('--model_dir', default='trained_model', help='path to save model')

    parser.add_argument('--ckpt', default='checkpoints/inflated/model.ckpt', type=str, help='path to previously saved model to load')

    parser.add_argument('--inference_mode', default=False, type=bool, help='whether to run inference only')

    parser.add_argument('--batch_size', default=2, type=int, help='the training batch size')

    parser.add_argument('--num_examples', default=50, type=int, help='the number of examples to run inference')

    parser.set_defaults()
    main(parser.parse_args())