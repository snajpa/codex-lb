use codex_lb_responses::stream::interpret;
use serde_json::Value;

#[test]
fn shared_stream_fixtures() {
    let cases: Vec<Value> = serde_json::from_str(include_str!("fixtures/stream-v1.json")).unwrap();
    for case in cases {
        let name = case["name"].as_str().unwrap();
        let event = interpret(case["block"].as_str().unwrap());
        assert_eq!(
            event.python_normalization,
            case["python_normalization"].as_bool().unwrap(),
            "{name}: handoff"
        );
        if !event.python_normalization {
            assert_eq!(
                event.text,
                case["native_text"].as_str().unwrap(),
                "{name}: text"
            );
            assert_eq!(
                event.event_type.as_deref(),
                case["native_type"].as_str(),
                "{name}: type"
            );
        }
    }
}

#[test]
fn terminal_headers_and_non_object_responses_do_not_complete_http() {
    for block in [
        "event: response.completed\ndata: {broken\n\n",
        "event: response.completed\ndata: {\"type\":\"response.output_text.delta\"}\n\n",
        "data: {\"type\":\"response.completed\",\"response\":[]}\n\n",
        "data: {\"type\":\"response.failed\"}\n\n",
        "data: {\"type\":\"response.incomplete\",\"response\":null}\n\n",
        "event: response.created\ndata: {\"type\":\"response.completed\",\"response\":[]}\n\n",
        "event: response.output_text.delta\ndata: {\"type\":\"response.completed\",\"response\":[]}\n\n",
    ] {
        assert!(!interpret(block).completes_http_stream(), "{block}");
    }
    for kind in [
        "response.completed",
        "response.failed",
        "response.incomplete",
    ] {
        let block = format!(
            "event: {kind}\ndata: {{\"type\":\"{kind}\",\"response\":{{\"id\":\"end\"}}}}\n\n"
        );
        assert!(interpret(&block).completes_http_stream(), "{block}");
        let mislabeled = format!(
            "event: response.created\ndata: {{\"type\":\"{kind}\",\"response\":{{\"id\":\"end\"}}}}\n\n"
        );
        assert!(
            interpret(&mislabeled).completes_http_stream(),
            "{mislabeled}"
        );
        assert_eq!(interpret(&mislabeled).event_type.as_deref(), Some(kind));
    }
}
