import yaml
import os
from collections import defaultdict


OPENAPI_FILE = "api.yaml"
OUTPUT_DIR = "api_client"


def load_openapi():
    with open(OPENAPI_FILE, "r") as f:
        return yaml.safe_load(f)


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    init_file = os.path.join(OUTPUT_DIR, "__init__.py")
    if not os.path.exists(init_file):
        open(init_file, "w").close()


def normalize_name(name):
    return name.replace("-", "_").lower()


def build_method_name(http_method, operation_id, path):
    if operation_id:
        return operation_id
    clean_path = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    return f"{http_method}_{clean_path}"


def extract_path_params(parameters):
    return [p["name"] for p in parameters if p.get("in") == "path"]


def extract_body_param(parameters):
    for p in parameters:
        if p.get("in") == "body":
            return p["name"]
    return None


def generate_api_classes(openapi):
    paths = openapi.get("paths", {})
    tag_to_endpoints = defaultdict(list)

    for path, methods in paths.items():
        for http_method, spec in methods.items():
            if http_method not in ["get", "post", "put", "delete"]:
                continue

            tag = spec["tags"][0]
            tag_to_endpoints[tag].append((path, http_method, spec))

    for tag, endpoints in tag_to_endpoints.items():
        generate_api_file(tag, endpoints)


def generate_api_file(tag, endpoints):
    class_name = f"{tag.capitalize()}Api"
    file_name = f"{normalize_name(tag)}_api.py"
    file_path = os.path.join(OUTPUT_DIR, file_name)

    with open(file_path, "w") as f:
        f.write("from api_client.base_http_client import BaseHttpClient\n\n\n")
        f.write(f"class {class_name}:\n")
        f.write("    def __init__(self, http_client: BaseHttpClient):\n")
        f.write("        self.http = http_client\n\n")

        for path, http_method, spec in endpoints:
            write_endpoint_method(f, path, http_method, spec)


def write_endpoint_method(f, path, http_method, spec):
    operation_id = spec.get("operationId")
    method_name = build_method_name(http_method, operation_id, path)
    parameters = spec.get("parameters", [])

    path_params = extract_path_params(parameters)
    body_param = extract_body_param(parameters)

    args = []
    args.extend(path_params)
    if body_param:
        args.append("body")

    args_str = ", ".join(args)
    if args_str:
        args_str = ", " + args_str

    f.write(f"    def {method_name}(self{args_str}):\n")

    formatted_path = path
    for p in path_params:
        formatted_path = formatted_path.replace(f"{{{p}}}", f"{{{p}}}")

    f.write(f"        path = f\"{formatted_path}\"\n")

    if body_param:
        f.write(
            f"        return self.http.request("
            f"\"{http_method.upper()}\", path, json=body)\n\n"
        )
    else:
        f.write(
            f"        return self.http.request("
            f"\"{http_method.upper()}\", path)\n\n"
        )


def main():
    ensure_output_dir()
    openapi = load_openapi()
    generate_api_classes(openapi)
    print("✅ API client generation completed")


if __name__ == "__main__":
    main()

