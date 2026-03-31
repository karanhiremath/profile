use thiserror::Error;

#[derive(Error, Debug)]
pub enum PcError {
    #[error("project '{0}' not found in {1}")]
    ProjectNotFound(String, String),

    #[error("directory does not exist: {0}")]
    DirNotFound(String),

    #[error("no active pc session (are you inside tmux?)")]
    NotInSession,

    #[error("no active pi sessions")]
    NoActiveSessions,

    #[error("no saved sessions in {0}")]
    NoSavedSessions(String),

    #[error("saved session '{0}' not found")]
    SaveNotFound(String),

    #[error("tmux not found — install with: brew install tmux")]
    TmuxNotFound,

    #[error("fzf not found — install with: brew install fzf")]
    FzfNotFound,

    #[error("tmux command failed: {0}")]
    TmuxCommand(String),

    #[error("picker cancelled")]
    PickerCancelled,

    #[error("session file corrupted: {0}")]
    SessionCorrupted(String),
}
