## ADDED Requirements

### Requirement: Distinguish working windows from hard input ceilings

The generic catalog MUST distinguish working and maximum windows from explicit
input ceilings. `metadata.input_context_window` MUST be the tighter declared
`input_context_window`/`max_input_tokens`, or unknown when absent. Bounds MUST be
positive non-boolean integers; malformed declarations MUST be rejected. Working
preferences MUST NOT create input ceilings. Output bounds, maximum context,
access filtering and native declarations MUST remain intact.

#### Scenario: A model supports a larger selected window

- **GIVEN** a normal window of 272000 and maximum context of 872000
- **AND** no explicit input ceiling
- **WHEN** a client discovers the generic models catalog
- **THEN** the normal and maximum windows remain 272000 and 872000
- **AND** the input ceiling is unknown rather than synthesized as 272000

#### Scenario: Explicit input limits survive a working-window override

- **GIVEN** explicit upstream input ceilings and a normal-window override
- **WHEN** the generic models catalog is rendered
- **THEN** the normal window reflects its sanctioned override
- **AND** the tighter explicit input ceiling remains authoritative

#### Scenario: An invalid explicit input limit is rejected

- **GIVEN** an explicit input limit that is not a positive non-boolean integer
- **WHEN** the generic model metadata is rendered
- **THEN** the malformed limit is rejected instead of becoming an unknown limit
