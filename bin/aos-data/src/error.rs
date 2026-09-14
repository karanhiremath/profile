use thiserror::Error;

#[derive(Debug, Error)]
pub enum AosError {
    #[error("{0}")]
    Msg(String),
    #[error("vault not found: {0}")]
    VaultMissing(String),
    #[error("class mismatch: argv0={argv0} requires {required}, manifest is {actual}")]
    ClassMismatch {
        argv0: String,
        required: String,
        actual: String,
    },
    #[error("refusing write outside vault: {0}")]
    Escape(String),
}

impl AosError {
    pub fn msg(s: impl Into<String>) -> Self {
        Self::Msg(s.into())
    }
}
