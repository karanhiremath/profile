//! WASI apply command: JSON on stdin, JSON on stdout. No host I/O.
use std::io::{self, Read};

fn main() {
    let mut input = String::new();
    if let Err(err) = io::stdin().read_to_string(&mut input) {
        eprintln!("{err}");
        std::process::exit(1);
    }
    match cos_voice_wasm::apply_json(input.trim()) {
        Ok(out) => println!("{out}"),
        Err(err) => {
            eprintln!("{err}");
            std::process::exit(1);
        }
    }
}
