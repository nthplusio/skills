"""Version-one document shapes, exported as JSON Schema by rules.py schema."""

VERSION = "1.0.0"


def obj(**properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def array(items):
    return {"type": "array", "items": items}


def ref(name):
    return {"$ref": f"#/$defs/{name}"}


TEXT = {"type": "string", "minLength": 1}
NULLABLE_TEXT = {"type": ["string", "null"], "minLength": 1}
ID = {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$"}
HASH = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
COMMIT = {"type": "string", "pattern": "^[0-9a-f]{40}([0-9a-f]{24})?$"}
REVISION = {"type": "integer", "minimum": 1}
V1 = {"type": "integer", "enum": [1]}


def enum(*values):
    return {"type": "string", "enum": list(values)}


WAIVER = obj(finding_id=ID, code_commit=COMMIT, expires_at=TEXT, reason=TEXT)


DEFS = {
    "authority": obj(id=ID, domain=ID, actor=TEXT, source=TEXT,
                     supersedes=NULLABLE_TEXT, authorized_by=NULLABLE_TEXT),
    "dependency": obj(registry_id=ID, domain=ID, repository=TEXT, commit=COMMIT),
    "config": obj(schema_version=V1, tool_version=enum(VERSION), tool_digest=HASH,
                  registry_id=ID, authorities=array(ref("authority")),
                  dependencies=array(ref("dependency"))),
    "source": obj(schema_version=V1, id=ID,
                  kind=enum("conversation", "questionnaire", "document"),
                  locator=TEXT, attribution=TEXT, excerpt=NULLABLE_TEXT,
                  authority_evidence=NULLABLE_TEXT),
    "relation": obj(type=enum("depends_on", "exception_to", "supersedes"),
                    rule_id=ID, revision=REVISION),
    "example": obj(given=TEXT, expect=TEXT),
    "claim": obj(claim_id=ID, source_id=ID, action=enum("enforce", "retire"),
                 statement=TEXT, kind=enum("validation", "default", "derivation", "matching",
                                          "precedence", "state-transition", "threshold", "ordering",
                                          "guarantee", "naming", "authorization", "prohibition"),
                 hierarchy=array(TEXT), scope=TEXT, condition=TEXT, outcome=TEXT,
                 exceptions=obj(knowledge=enum("unknown", "explicit"), items=array(TEXT)),
                 questions=array(TEXT), examples=array(ref("example")),
                 relations=array(ref("relation"))),
    "target": obj(rule_id=ID, revision=REVISION, digest=HASH),
    "waiver": WAIVER,
    "decision": obj(schema_version=V1, id=ID, kind=enum("approve", "reject", "waive"),
                    authority_id=ID, actor=TEXT, source_id=ID, decided_at=TEXT,
                    effective_at=TEXT, targets=array(ref("target")),
                    waiver={**WAIVER, "type": ["object", "null"]}),
    "mapping": obj(observation_id=ID, status=enum("matched", "ambiguous", "unmatched"),
                   candidates=array(ref("target"))),
    "evidence": obj(locator=TEXT, text=TEXT),
    "assessment": obj(id=ID, rule_id=ID, revision=REVISION,
                      code_side=enum("base", "head"), policy_side=enum("base", "head"),
                      outcome=enum("conforms", "violation", "confirmed-conflict", "potential-conflict", "not-assessed"),
                      method=enum("executed-test", "source-review", "semantic-review", "not-assessed"),
                      evidence=array(ref("evidence")), scenario=NULLABLE_TEXT,
                      waiver_id=NULLABLE_TEXT),
    "audit": obj(schema_version=V1, base_commit=COMMIT, head_commit=COMMIT,
                 base_registry_digest=HASH, head_registry_digest=HASH, as_of=TEXT,
                 binding_ids=array(HASH),
                 scope=array(TEXT), exclusions=array(TEXT), limitations=array(TEXT),
                 assessments=array(ref("assessment")),
                 unrecorded=array(obj(description=TEXT, evidence=array(ref("evidence"))))),
}
DEFS["revision"] = obj(revision=REVISION, **DEFS["claim"]["properties"])
DEFS["rule"] = obj(schema_version=V1, id=ID, domain=ID, revisions=array(ref("revision")))
DEFS["capture"] = obj(source=ref("source"), rule_id=ID, domain=ID, claim=ref("claim"))
DEFS["binding"] = obj(schema_version=V1, id=HASH, catalogue_digest=HASH, code_commit=COMMIT,
                      catalogue={"type": "object"}, mappings=array(ref("mapping")))
DEFS["finding"] = obj(**DEFS["assessment"]["properties"],
                      disposition=enum("must-resolve", "advisory", "waived", "approved-policy-change", "resolved-in-head"))
DEFS["report"] = obj(**{**DEFS["audit"]["properties"], "assessments": array(ref("finding"))},
                     changed_paths=array(TEXT), stale_bindings=array(HASH),
                     external_dependencies_not_assessed=array(ref("dependency")),
                     ci_gate=enum("not-evaluated"), evidence_trust=TEXT,
                     summary=enum("must-resolve", "review-required", "reported-conformance-within-scope"))


def schema():
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": f"Business rules contract {VERSION}", "$defs": DEFS}


def check(value, shape, path="document"):
    """Validate the closed keyword subset used above; no external schema loading."""
    if "$ref" in shape:
        return check(value, DEFS[shape["$ref"].split("/")[-1]], path)
    types = {"object": dict, "array": list, "string": str, "integer": int, "null": type(None)}
    allowed = shape.get("type", list(types))
    allowed = [allowed] if isinstance(allowed, str) else allowed
    if not any(type(value) is types[t] for t in allowed):
        raise ValueError(f"{path}: expected {' or '.join(allowed)}")
    if "enum" in shape and value not in shape["enum"]:
        raise ValueError(f"{path}: expected one of {shape['enum']}")
    if isinstance(value, dict) and "properties" in shape:
        missing = set(shape["required"]) - value.keys()
        extra = value.keys() - shape["properties"].keys()
        if missing or extra:
            raise ValueError(f"{path}: missing {sorted(missing)}, unexpected {sorted(extra)}")
        for key, item in value.items():
            check(item, shape["properties"][key], f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            check(item, shape["items"], f"{path}[{index}]")
    elif isinstance(value, str):
        import re
        if len(value.strip()) < shape.get("minLength", 0):
            raise ValueError(f"{path}: text must not be empty")
        if "pattern" in shape and not re.fullmatch(shape["pattern"], value):
            raise ValueError(f"{path}: invalid identifier or digest")
    elif type(value) is int and value < shape.get("minimum", value):
        raise ValueError(f"{path}: below minimum")


def validate(kind, value):
    check(value, DEFS[kind], kind)
