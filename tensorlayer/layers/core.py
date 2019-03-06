#! /usr/bin/python
# -*- coding: utf-8 -*-

import inspect
import six

from abc import ABCMeta, abstractmethod

import numpy as np

import tensorflow as tf
import tensorlayer as tl

from tensorlayer.layers.utils import list_remove_repeat, get_variable_with_initializer

from tensorlayer import logging

from tensorlayer.decorators import deprecated_alias
from tensorlayer.decorators import protected_method
from tensorlayer.decorators import private_method

__all__ = [
    'Layer',
    'ModelLayer',
    'LayerList'
]

_global_layer_name_dict = {}  # TODO: better implementation?


def _addindent(s_, numSpaces):
    s = s_.split('\n')
    # don't do anything for single-line stuff
    if len(s) == 1:
        return s_
    first = s.pop(0)
    s = [(numSpaces * ' ') + line for line in s]
    s = '\n'.join(s)
    s = first + '\n' + s
    return s

class Layer(object):
    #FIXME: documentation update needed
    """The basic :class:`Layer` class represents a single layer of a neural network.

    It should be subclassed when implementing new types of layers.

    Parameters
    ----------
    name : str or None
        A unique layer name. If None, a unique name will be automatically assigned.

    Methods
    ---------
    __init__()
        Initializing the Layer.
    __call__()
        (1) Building the Layer if necessary. (2) Forwarding the computation.
    weights()
        Return a list of Tensor which are all trainable weights of this Layer.
    build()
        Abstract method. Build the Layer. All trainable weights should be defined in this function.
    forward()
        Abstract method. Forward computation and return computation results.

    """

    def __init__(self, name=None, *args, **kwargs):
        """
        Initializing the Layer.

        :param name: str or None
        """

        # Layer constants
        for key in kwargs.keys():
            setattr(self, key, self._argument_dict_checkup(kwargs[key]))

        # self.act = act if act not in [None, tf.identity] else None

        # Auto naming if the name is not given
        global _global_layer_name_dict
        if name is None:
            prefix = self.__class__.__name__.lower()
            if _global_layer_name_dict.get(prefix) is not None:
                _global_layer_name_dict[prefix] += 1
                name = prefix + '_' + str(_global_layer_name_dict[prefix])
            else:
                _global_layer_name_dict[prefix] = 0
                name = prefix

        self.name = name

        # Layer's input and outputs
        self.inputs = None
        self.outputs = None
        self._inputs_shape_mem = None
        self._outputs_shape_mem = None

        self._input_layer = None

        # Layer building state
        self._built = False

        # Layer weight state
        self._weights = None

        # Layer training state
        self.is_train = True

    @property
    def _inputs_shape(self):
        if self.inputs is not None:
            if isinstance(self.inputs, list):
                self._inputs_shape_mem = [t.get_shape().as_list() for t in self.inputs]
            else:
                self._inputs_shape_mem = self.inputs.get_shape().as_list()
        return self._inputs_shape_mem

    @property
    def _outputs_shape(self):
        if self.outputs is not None:
            if isinstance(self.outputs, list):
                self._outputs_shape_mem = [t.get_shape().as_list() for t in self.outputs]
            else:
                self._outputs_shape_mem = self.outputs.get_shape().as_list()
        return self._outputs_shape_mem

    @property
    def weights(self):
        return self._weights

    def __call__(self, prev_layer, **kwargs):
        """
        (1) Build the Layer if necessary.
        (2) Forward the computation and return results.

        :param prev_layer: np.ndarray, Tensor, Layer, list of Layers
        :param kwargs:
        :return: Layer
        """

        if self.__class__.__name__ in tl.layers.inputs.__all__:
            # 1. for input layers
            # Input layers should use tf.convert_to_tensor to make sure the inputs is converted into tf.Tensor

            self.inputs = tf.convert_to_tensor(prev_layer)
            self._input_layer = None
            self._built = True
            self.build(self._inputs_shape)
            self.outputs = self.forward(self.inputs, **kwargs)

        elif isinstance(prev_layer, Layer):
            # 2. for normal layer have only one input i.e. Dense
            # Hint : list(), dict() is pass by value (shallow), without them,
            # it is pass by reference.

            self.inputs = prev_layer.outputs
            self._input_layer = prev_layer

            if not self._built:
                self.build(self._inputs_shape)
                self._built = True

            self.outputs = self.forward(self.inputs, **kwargs)

        elif isinstance(prev_layer, list):
            # 3. for layer have multiply inputs i.e. Concat

            self.inputs = [layer.outputs for layer in prev_layer]
            self._input_layer = prev_layer # FIXME: not sure how to deal with it

            # FIXME: only support concat/elementwise, where build does nothing
            if not self._built:
                self._built = True

            self.outputs = self.forward(self.inputs, **kwargs)

        else:
            raise AssertionError("Invalid input type: %s" % type(prev_layer))

        return self

    def _release_memory(self):
        """
        WARINING: This function should be called with great caution.

        self.inputs and self.outputs will be set as None but not deleted in order to release memory.
        """

        _ = self._inputs_shape # save input shape before inputs become None
        _ = self._outputs_shape # save outputs shape before outputs become None
        self.inputs = None
        self.outputs = None

    def _set_mode_for_layers(self, is_train):
        """ Set training/evaluation mode for the Layer"""
        self.is_train = is_train

    def _get_weights(self, var_name, shape, init=tl.initializers.random_normal()):
        """ Get trainable variables. """
        weight = get_variable_with_initializer(
            scope_name=self.name, var_name=var_name, shape=shape, init=init
        )
        if self._weights is None:
            self._weights = list()
        self._weights.append(weight)  # Add into the weight collection
        return weight

    @abstractmethod
    def build(self, inputs_shape):
        """
        An abstract method which should be overwritten in derived classes
        to define all necessary trainable weights of the layer.

        self.built should be set as True after self.build() is called.

        :param inputs_shape: tuple
        """
        raise Exception("The build(self, inputs_shape) method must be implemented by inherited class")

    @abstractmethod
    def forward(self, inputs):
        # FIXME: documentation needed
        """
        An abstract method which should be overwritten in derived classes
        to define forward feeding operations of the layer.

        :param inputs: Tensor
        :return: Tensor
        """
        raise Exception("The forward method must be implemented by inherited class")

    def __repr__(self):
        reprstr = "Layer"
        return reprstr

    def __setitem__(self, key, item):
        raise TypeError("The Layer API does not allow to use the method: `__setitem__`")

    def __delitem__(self, key):
        raise TypeError("The Layer API does not allow to use the method: `__delitem__`")

    @private_method
    def _argument_dict_checkup(self, args):

        if not isinstance(args, dict) and args is not None:
            raise AssertionError(
                "One of the argument given to %s should be formatted as a dictionary" % self.__class__.__name__
            )

        return args if args is not None else {}


class ModelLayer(Layer):
    # TODO: documentation
    '''
    Documentation pending
    '''

    def __init__(self, model):
        super(ModelLayer, self).__init__(name="%s_layer" % model.name)

        self.model = model

        # Layer input outputs
        # FIXME: model.inputs can be a list
        self.inputs = model.inputs.outputs
        # FIXME: model.outputs can be a list
        self.outputs = model.forward(self.inputs)

        self._input_layer = model.inputs

        # Layer building state
        self._built = True

        # Layer weight state
        self._weights = model.weights

        # Layer training state
        self.is_train = True

        logging.info(
            "ModelLayer %s from Model: %s" %
            (self.name, self.model.name)
        )

    def __repr__(self):
        tmpstr = 'ModelLayer' + '(\n'

        modstr = self.model.__repr__()
        modstr = _addindent(modstr, 2)

        tmpstr += modstr + ')'
        return tmpstr

    def build(self, inputs_shape):
        pass

    def forward(self, inputs):
        return self.model.forward(inputs)

    def _set_mode_for_layers(self, is_train):
        self.is_train = is_train
        return self.model._set_mode_for_layers(is_train)

    def _release_memory(self):
        '''
        WARINING: This function should be called with great caution.

        self.inputs and self.outputs will be set as None but not deleted.

        '''
        super(ModelLayer, self)._release_memory()
        self.model.release_memory()

'''
class SequentialLayer(Layer):


    def __init__(self, prev_layer, following_layers, name=None):

        super(SequentialLayer, self).__init__(name=name)

        # Layer input outputs
        self.inputs = prev_layer.outputs
        self._input_layer = prev_layer

        # Layer weight state
        self._weights = list()

        # TODO: check type of following layers
        self.following_layer = list()
        in_layer = prev_layer
        for layer in following_layers:
            nlayer = layer(in_layer)
            self.following_layer.append(nlayer)
            self._weights.extend(nlayer.weights)
            in_layer = nlayer

        self.outputs = self.forward(self.inputs)

        # Layer building state
        self._built = True

        logging.info(
            "SequentialLayer %s including layers [%s]" %
            (self.name, ', '.join([layer.name for layer in self.following_layer]))
        )

    def build(self, inputs_shape):
        pass

    def forward(self, inputs):
        z = inputs
        for layer in self.following_layer:
            z = layer.forward(z)

       return z
'''


class LayerList(Layer):
    # TODO: documentation
    '''
    Documentation pending
    '''
    def __init__(self, layers:list, name=None):
        super(LayerList, self).__init__(name=name)
        self.layers = layers

        is_built = True
        for layer in self.layers:
            if layer._built == False:
                is_built = False
            if layer._built == True and layer.weights is not None:
                # some layers in the list passed in have already been built
                # e.g. using input shape to construct layers in dynamic eager
                if self._weights == None:
                    self._weights = list()
                self._weights.extend(layer.weights)
        if is_built == True:
            self._built = True

        logging.info(
            "LayerList %s including layers [%s]" %
            (self.name, ', '.join([layer.name for layer in self.layers]))
        )

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            return LayerList(list(self.layers)[idx])
        else:
            return self.layers[idx]

    def __len__(self):
        return len(self.layers)

    def __repr__(self):
        tmpstr = 'LayerList' + '(\n'
        for idx, layer in enumerate(self.layers):
            modstr = layer.__repr__()
            modstr = _addindent(modstr, 2)
            tmpstr = tmpstr + '  (' + str(idx) + '): ' + modstr + '\n'

        tmpstr = tmpstr + ')'
        return tmpstr

    def build(self, inputs_shape):
        in_layer = self._input_layer
        for layer in self.layers:
            is_build = layer._built
            nlayer = layer(in_layer)
            if is_build == False and layer.weights is not None:
                if self._weights == None:
                    self._weights = list()
                self._weights.extend(layer.weights)
            layer._built = True
            in_layer = nlayer

    def forward(self, inputs):
        z = inputs
        for layer in self.layers:
            z = layer.forward(z)
        return z

    def _set_mode_for_layers(self, is_train):
        self.is_train = is_train
        for layer in self.layers:
            if isinstance(layer, ModelLayer):
                layer._set_mode_for_layers(is_train)
            elif isinstance(layer, LayerList):
                layer._set_mode_for_layers(is_train)
            else:
                layer.is_train = is_train

    def _release_memory(self):
        '''
        WARINING: This function should be called with great caution.

        self.inputs and self.outputs will be set as None but not deleted.

        '''
        super(LayerList, self)._release_memory()
        for layer in self.layers:
            layer._release_memory()



# if __name__ == '__main__':
#
#     from tensorlayer.layers import Input, Dense, Dropout, LayerList
#     from tensorlayer.models import Model
#
#     class mynet(Model):
#
#         def __init__(self):
#             super(mynet, self).__init__()
#
#             self.layers = LayerList([
#                 Input([None, 784]),
#                 Dropout(keep=0.8),
#                 Dense(n_units=800, act=tf.nn.relu, in_channels=784),
#                 Dense(n_units=800, act=tf.nn.relu, in_channels=800)
#             ])
#
#         def forward(self, x):
#             z = x
#             for i in range(3):
#                 z = self.layers[i](z)
#             return z
#
#     def get_model(inputs_shape):
#         ni = Input(inputs_shape)
#         nn = LayerList([
#             Dropout(keep=0.8),
#             Dense(n_units=800, act=tf.nn.relu),
#             Dropout(keep=0.8),
#             Dense(n_units=800, act=tf.nn.relu)
#         ])(ni)
#
#         M = Model(inputs=ni, outputs=nn)
#
#         return M
#
#     #net = mynet()
#     net = get_model([None, 784])
#     print(net.weights)
#     print(net.layer_dict['layerlist']._built)
