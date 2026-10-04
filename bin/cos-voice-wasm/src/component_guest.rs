//! WIT guest for Wasmex.Components. Compiled only for wasm32.

wit_bindgen::generate!({
    world: "apply",
    path: "wit",
});

struct Component;

impl Guest for Component {
    fn apply_json(input: String) -> Result<String, String> {
        crate::apply_json(&input)
    }
}

export!(Component);
