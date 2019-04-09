#!/usr/bin/env python
# -*- coding: utf-8 -*-

try:
    from setuptools import setup
except ImportError:
    print('No setuptools installed, use distutils')
    from distutils.core import setup

with open('requirements.txt') as f:
    required = f.read().splitlines()

setup(
    name='multi_editor',
    packages=[
        'multi_editor',
    ],
    include_package_data=True,
    install_requires=required,
    version='1.0',
    description='Theia IDE multi editor',
    classifiers=[
        'Programming Language :: Python',
        'Development Status :: 4 - Beta',
        'Environment :: Other Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    long_description='''\
'''
)
