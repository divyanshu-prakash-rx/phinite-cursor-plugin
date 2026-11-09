"""plugin_probe_deploy_echo — test tool for the Claude plugin (no side effects)."""


def main(inputs, env_variables):
    keys = sorted((inputs or {}).keys())
    return {"output": {"ok": True, "input_keys": keys}, "capture_variables": {"probe_result": ",".join(keys)}}
