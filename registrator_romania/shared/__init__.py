import envyaml


def get_config() -> envyaml.EnvYAML:
    return envyaml.EnvYAML(
        "config.yml", ".env", include_environment=False, flatten=False
    )
