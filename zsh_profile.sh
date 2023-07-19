source ~/profile/myprofile.sh

alias reload="source ~/.zshrc && echo 'ZSH Profile Reloaded'"

autoload -U colors && colors
autoload -Uz promptinit && promptinit

# initialize completio
autoload -Uz compinit
compinit

# Load version control information
autoload -Uz vcs_info

# Format the vcs_info_msg_0_ variable
zstyle ':vcs_info:git:*' formats '%b'
 
# Set up the prompt (with git branch name)
setopt PROMPT_SUBST

precmd() {
    vcs_info
    if [[ -n ${vcs_info_msg_0_} ]]; then
        STATUS='$(command git status --porcelain 2> /dev/null | tail -n1)'
        if [[ -n $STATUS ]]; then
            PROMPT="%F{9}%D{%Y-%m-%d %H:%M:%S}%f %F{11}|%f %F{12}%n%f%F{9}@%m%f %F{11}|%f %F{9}%~%f $prompt_newline%F{9}(%f%F{9}${vcs_info_msg_0_}%f%F{9})%f %F{11}>%f %F{15}"
        else
            PROMPT="%F{9}%D{%Y-%m-%d %H:%M:%S}%f %F{11}|%f %F{12}%n%f%F{9}@%m%f %F{11}|%f %F{9}%~%f $prompt_newline%F{9}(%f%F{10}${vcs_info_msg_0_}%f%F{9})%f %F{11}>%f %F{15}"
        fi
    else
        PROMPT="%F{9}%D{%Y-%m-%d %H:%M:%S}%f %F{11}|%f %F{12}%n%f%F{9}@%m%f %F{11}|%f %F{9}%~%f $prompt_newline %F{11}>%f %F{15}"
    fi
}

bindkey "^[[H" beginning-of-line
bindkey "^[[F" end-of-line
bindkey  "^[[3~"  delete-char
