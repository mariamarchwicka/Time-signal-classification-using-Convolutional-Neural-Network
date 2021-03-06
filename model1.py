# -*- coding: utf-8 -*-
"""
Created on Thu Feb 28 20:16:02 2019

@author:    DATAmadness
Github:     https://github.com/datamadness
Blog:       ttps://datamadness.github.io
Description: CNN for VSB power line discharge classification using SFFT of time domain data
DataSource: https://www.kaggle.com/c/vsb-power-line-fault-detection/data
"""

import tensorflow as tf
import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics import accuracy_score
from sklearn.metrics import confusion_matrix
import os
#%% Specify parameters
batch_size = 40                    #Note that large batch sized is linked to sharp gradients
training_steps = 10                #Number of batches to train on
num_epochs = 60                    #None to repeat dataset until all steps are executed
data_path = r'../data/'
output_path_train = r'./TFR_train_sfft/'
output_path_eval = r'./TFR_eval_sfft/'
predict_folder = r'./TFR_predict_sfft/'

eval_folder = output_path_eval      #Subfolder containing TFR files with evaluation data
train_folder = output_path_train   #Subfolder containing TFR files with training data

#%% Building the CNN Classifier
def cnn_model_fn(features, labels, mode):
  """Model function for CNN."""
  if mode == tf.estimator.ModeKeys.PREDICT:
      pass
  else:
      labels=tf.reshape(labels,[-1,1])
  input_layer = tf.reshape(features["signal_data"], [-1, 240, 200,1])
  print(input_layer)

  # Convolutional Layer #1
  conv1 = tf.compat.v1.layers.conv2d(
      inputs=input_layer,
      filters=32,
      kernel_size=[5, 5],
      strides=(2, 2),
      padding="same",
      activation=tf.nn.relu)
      #Output -1,120,100,32
  print(conv1)

  # Convolutional Layer #2 and Pooling Layer #2
  conv2 = tf.compat.v1.layers.conv2d(
      inputs=conv1,
      filters=64,
      kernel_size=[3, 3],
      padding="same",
      activation=tf.nn.relu)
  #Output -1,120,100,64
  pool2 = tf.compat.v1.layers.max_pooling2d(inputs=conv2, pool_size=[2, 2], strides=2)
  #Output -1,60,50,64
  dropout = tf.compat.v1.layers.dropout(
      inputs=pool2, rate=0.1, training=mode == tf.estimator.ModeKeys.TRAIN)

  # Convolutional Layer #3 and Pooling Layer #3
  conv3 = tf.compat.v1.layers.conv2d(
      inputs=dropout,
      filters=128,
      kernel_size=[3, 3],
      padding="same",
      activation=tf.nn.relu)
  #Output -1,60,50,128
  pool3 = tf.compat.v1.layers.max_pooling2d(inputs=conv3, pool_size=[2, 2], strides=2)
  #Output -1,30,25,128
  dropout2 = tf.compat.v1.layers.dropout(
      inputs=pool3, rate=0.1, training=mode == tf.estimator.ModeKeys.TRAIN)

  # Convolutional and pooling Layer #4
  conv4 = tf.compat.v1.layers.conv2d(
      inputs=dropout2,
      filters=200,
      kernel_size=[3, 3],
      padding="same",
      activation=tf.nn.relu)
  #Output -1,30,25,200
  pool4 = tf.compat.v1.layers.max_pooling2d(inputs=conv4, pool_size=[2, 2], strides=2)
  #Output -1,15,12,200

  # Dense Layer
  pool4_flat = tf.reshape(pool4, [-1, 15 * 12 * 200])
  dense = tf.compat.v1.layers.dense(inputs=pool4_flat, units=4096, activation=tf.nn.relu)

  dropout3 = tf.compat.v1.layers.dropout(
      inputs=dense, rate=0.2, training=mode == tf.estimator.ModeKeys.TRAIN)

  dense2 = tf.compat.v1.layers.dense(inputs=dropout3, units=2048, activation=tf.nn.relu)

  dropout4 = tf.compat.v1.layers.dropout(
      inputs=dense2, rate=0.2, training=mode == tf.estimator.ModeKeys.TRAIN)

  # Logits Layer
  logits = tf.compat.v1.layers.dense(inputs=dropout4, units=1)

  predictions = {
      # Generate predictions (for PREDICT and EVAL mode)
      "classes": tf.round(tf.nn.sigmoid(logits)),
      "probabilities": tf.nn.sigmoid(logits, name="probs_tensor"),
      "signal_id": tf.reshape(features["signal_ID"],[-1,1])
  }


  if mode == tf.estimator.ModeKeys.PREDICT:
    return tf.estimator.EstimatorSpec(mode, predictions=predictions)

  loss = tf.losses.sigmoid_cross_entropy(multi_class_labels=labels, logits=logits)


  # Configure the Training Op (for TRAIN mode)
  if mode == tf.estimator.ModeKeys.TRAIN:

    # Calculate Loss (for both TRAIN and EVAL modes) via cross entropy

    optimizer = tf.optimizers.SGD(learning_rate=0.001)
    train_op = optimizer.minimize(
        loss=loss,
        global_step=tf.train.get_global_step())
    return tf.estimator.EstimatorSpec(mode=mode, loss=loss, train_op=train_op)

  # Add evaluation metrics (for EVAL mode)
  eval_metric_ops = {
          "accuracy": tf.metrics.auc(
          labels=labels, predictions=predictions["classes"])

  }
  return tf.estimator.EstimatorSpec(
      mode=mode, loss=loss, eval_metric_ops=eval_metric_ops)

#%% CREATE ESTIMATOR

# Create the Estimator
discharge_classifier = tf.estimator.Estimator(
    model_fn=cnn_model_fn, model_dir="/tmp4096/sfft_convnet_model")

#%% Set Up a Logging Hook

# Set up logging for predictions
tensors_to_log = {"probabilities": "probs_tensor"}

logging_hook = tf.estimator.LoggingTensorHook(
    tensors=tensors_to_log, every_n_iter=50)

#%% Input function for training data

def dataset_input_fn(subfolder, batch_size, train = False, num_epochs=None):

    filenames = [file for file in os.listdir(subfolder) if file.endswith('.tfrecord')]
    filenames = [os.path.join(subfolder, file) for file in filenames]
    dataset = tf.data.TFRecordDataset(filenames)

    #Create record extraction function
    def parser(record):
        features = {
            'signal': tf.io.FixedLenFeature([50000], dtype=tf.float32),
            'signal_ID': tf.io.FixedLenFeature([], dtype=tf.int64),
            'measurement_ID': tf.io.FixedLenFeature([], dtype=tf.int64),
            'label': tf.io.FixedLenFeature([], dtype=tf.int64)}
        parsed = tf.io.parse_single_example(record, features)

        # Perform additional preprocessing on the parsed data.
        bw_data = tf.reshape(tf.sqrt(parsed['signal']), [-1, 250, 200])
        bw_data = tf.slice(bw_data, [0, 2, 0], [1, 240, 200])

        # Min max normalization
        bw_data =  tf.compat.v1.div(
                tf.subtract(
                    bw_data,
                    tf.reduce_min(bw_data)
                ),
                tf.subtract(
                    tf.reduce_max(bw_data),
                    tf.reduce_min(bw_data)
                )
        )
        bw_data = tf.round(bw_data)

        signal_data = tf.reshape(parsed['signal'], [-1, 250, 200])
        #remove low frequency components
        signal_data = tf.slice(signal_data, [0, 2, 0], [1, 240, 200])

        #Normalize and scale data
        qube = tf.fill([240,200],1/3)
        signal_data = tf.pow(signal_data,qube)
        signal_data = tf.image.per_image_standardization(signal_data)

        norm_max = tf.fill([240,200],6.0)
        signal_data = tf.divide(signal_data,norm_max)

        label = tf.cast(parsed["label"], tf.int32)

        return {"signal_data": signal_data, "bw_data": bw_data, "signal_ID": parsed["signal_ID"]}, label

    # Use `Dataset.map()` to build a pair of a feature dictionary and a label
    # tensor for each example.
    dataset = dataset.map(parser)

    #Shuffle data if in training mode
    if train:
        dataset = dataset.shuffle(buffer_size=batch_size*2)  #Shuffles along first dimension(rows)(!)  and selects from buffer
    dataset = dataset.batch(batch_size)
    dataset = dataset.repeat(num_epochs)

    # Each element of `dataset` is tuple containing a dictionary of features
    # (in which each value is a batch of values for that feature), and a batch of
    # labels.
    return dataset

#%% Train the clasifier
discharge_classifier.train(
    input_fn=lambda : dataset_input_fn(train_folder, train = True, batch_size = batch_size, num_epochs=num_epochs),
    steps=training_steps,
    hooks=[logging_hook])

#%% Evaluate the model
eval_results = discharge_classifier.evaluate(
        input_fn=lambda : dataset_input_fn(eval_folder, train = False, batch_size = batch_size, num_epochs=1))
print(eval_results)

#%% Predict
results = discharge_classifier.predict(
        input_fn=lambda : dataset_input_fn(predict_folder, train = False, batch_size = batch_size, num_epochs=1))
results = list(results)

#%% Get labels from TFR files
with tf.Session() as sess:
    dataset = dataset_input_fn(eval_folder, train = False, batch_size = 2178, num_epochs=2)
    iterator = dataset.make_initializable_iterator()
    sess.run(iterator.initializer)
    batch = iterator.get_next()
    labels = batch[1].eval()
    signal_ids = batch[0]["signal_ID"].eval()

#%% MCC calculations
#predicted_probs = np.array(list(map(lambda p: p['probabilities'],results)), dtype=np.float32)
#predicted_class = np.array(list(map(lambda c: c['classes'],results)), dtype=np.int16)

#Predict classes based on predicted probabilities and threshold
def score_model_measurement(probs,threshold):
    predicted = np.array([1 if x > threshold else 0 for x in probs[:,0]])
    return predicted

#Print confusion matric and calculate Matthews correlation coefficient (MCC)
def print_metrics(labels, scores):
    conf = confusion_matrix(labels, scores)
    print('                 Confusion matrix')
    print('                 Score positive    Score negative')
    print('Actual positive    %6d' % conf[1,1] + '             %5d' % conf[1,0])
    print('Actual negative    %6d' % conf[0,1] + '             %5d' % conf[0,0])
    print('')
    print('Accuracy  %0.2f' % accuracy_score(labels, scores))

    TP = conf[1,1]
    TN = conf[0,0]
    FP = conf[0,1]
    FN = conf[1,0]
    MCC = ((TP*TN) - (FP*FN)) / np.sqrt((TP+FP)*(TP+FN)*(TN+FP)*(TN+FN))
    print('MCC = %0.2f' %MCC)
    return MCC

#Print confusion matrix and Matthews correlation coefficient (MCC) based on labels vs predictions
#predictions = score_model_measurement(predicted_probs,0.5)
#MCC = print_metrics(labels, predictions)

#%% Training run with a custom validation each epoch

loss_plot = np.array([])
accuracy_plot = np.array([])
MCC_plot = np.array([])
epochs_plot = np.array([])

for i in range(num_epochs):

    discharge_classifier.train(
    input_fn=lambda : dataset_input_fn(train_folder, train = True, batch_size = batch_size, num_epochs=1),
    steps=None)

    eval_results = discharge_classifier.evaluate(
        input_fn=lambda : dataset_input_fn(eval_folder, train = False, batch_size = batch_size, num_epochs=1))

    results = discharge_classifier.predict(
        input_fn=lambda : dataset_input_fn(eval_folder, train = False, batch_size = batch_size, num_epochs=1))
    predicted_probs = np.array(list(map(lambda p: p['probabilities'],results)), dtype=np.float32)

    scores = score_model_measurement(predicted_probs,0.5)
    MCC = print_metrics(labels, scores)

    loss_plot = np.append(loss_plot,eval_results['loss'])
    accuracy_plot = np.append(accuracy_plot,eval_results['accuracy'])
    if np.isnan(MCC):
        MCC=0
    MCC_plot = np.append(MCC_plot,MCC)
    epochs_plot = np.append(epochs_plot,i)

    plt.figure(figsize=(10,6))
    plt.plot(epochs_plot,loss_plot,color='lightcoral', marker='o', linestyle='--', linewidth=1.5, markersize=5, label='loss')
    plt.plot(epochs_plot,accuracy_plot,color='steelblue', marker='s', linestyle='-.', linewidth=1.5, markersize=5,label='accuracy')
    plt.plot(epochs_plot,MCC_plot,color='seagreen', marker='^', linestyle='-', linewidth=1.5, markersize=5,label='MCC')


    plt.xlabel('Epoch')
    plt.legend()
    plt.savefig("Learning_plot.png")
    plt.show()
