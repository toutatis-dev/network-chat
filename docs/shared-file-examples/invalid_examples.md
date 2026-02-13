# Invalid Row Examples

These examples should be rejected or skipped by readers.

## Event row with unknown type (reject row)

```json
{"v":1,"ts":"2026-02-13T12:00:00","type":"unknown_type","author":"alice","text":"x"}
```

## Event row with non-string author/text (reject row)

```json
{"v":1,"ts":"2026-02-13T12:00:00","type":"chat","author":123,"text":false}
```

## Event row with future schema version (reject row)

```json
{"v":999,"ts":"2026-02-13T12:00:00","type":"chat","author":"alice","text":"x"}
```

## Memory row malformed JSON (skip row)

```text
{"id":"mem_1","summary":"missing closing brace"
```
