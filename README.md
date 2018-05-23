# Profile

## Using this profile

### Automated Installation
1. Clone this repository wherever you want
2. Navigate to the repository
3. Run the following to start the install script
  
  ```bash
  ./install.sh
  ```

4. Reload your bash profile using
 
 ```bash
  source ~/.bash_profile
  ```
### Manual Installation

1. Clone this repository wherever you want
2. Add the following line to your `~/.bash_profile`
  
  ```bash
  source  [PATH TO REPO]/myprofile.sh
  ```

3. Add the following line to your `~/.vimrc`
  
  ```bash
  source [PATH TO REPO]/vimprofile.sh
  ```

4. Add the following line to your `~/.tmux.conf`

  ```bash
  source-file [PATH TO REPO]/tmuxprofile.conf
  ```

5. Reload your bash profile using
  
  ```bash
  source ~/.bash_profile
  ```

