from setuptools import setup, find_packages

setup(
    name='obi',
    version='0.1.0',
    description='A package for creating and managing simulation campaigns',
    author='Your Name',
    author_email='your.email@example.com',
    url='https://github.com/yourusername/obi',
    packages=find_packages(),
    install_requires=[
        # List your package dependencies here
    ],
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
)