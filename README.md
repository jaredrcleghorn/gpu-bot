# gpu-bot

## Installation

You will need [Python](https://www.python.org/), [Pipenv](https://pipenv.pypa.io/en/latest/), and
[Google Chrome](https://www.google.com/chrome/index.html). On [Mac](https://www.apple.com/mac/), you
can install all three using [Homebrew](https://brew.sh/). To install Homebrew, run

```shell
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Then, to install Python and Pipenv, run

```shell
brew install python pipenv
```

Next, to install Google Chrome, run

```shell
brew install --cask google-chrome
```

Finally, to install dependencies, move into the project folder and run

```shell
pipenv install
```

## Configuration

Fill out the `config.json` file. Proxies should be in the format `username:password@ip:port`.

## Usage

To start the bot, run

```shell
pipenv run start
```
