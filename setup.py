from setuptools import setup

with open('README.md') as f:
    long_description = f.read()

VERSION="0.0.2"

setup(
    name='plexwebsocket',
    version=VERSION,
    description='Support for issuing callbacks in response to Plex websocket client updates.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/jjlawren/python-plexwebsocket/',
    license='MIT',
    author='Jason Lawrence',
    author_email='jjlawren@users.noreply.github.com',
    platforms='any',
    py_modules=['plexwebsocket'],
    install_requires=['aiohttp'],
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ]
)
