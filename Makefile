PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

.PHONY: lint typecheck test test-integration test-load test-phase0 test-blender-smoke package-check schema-export schema-check run-stdio run-http-unsafe controller-smoke

lint:
	$(PYTHON) -m ruff check .

typecheck:
	$(PYTHON) -m mypy

test:
	$(PYTHON) -m pytest -m "not soak"

test-integration:
	$(PYTHON) -m pytest -m "integration and not soak"

test-load:
	$(PYTHON) -m pytest -m soak -q

test-phase0:
	$(PYTHON) -m pytest tests/test_acceptance_stdio.py -q

test-blender-smoke:
	@blender_bin="$$BLENDER_MCP_BLENDER_BINARY"; \
	if [ -z "$$blender_bin" ] && command -v blender >/dev/null 2>&1; then blender_bin="$$(command -v blender)"; fi; \
	if [ -z "$$blender_bin" ] && [ -x /Applications/Blender.app/Contents/MacOS/Blender ]; then blender_bin=/Applications/Blender.app/Contents/MacOS/Blender; fi; \
	if [ -z "$$blender_bin" ]; then echo "Blender binary not found. Set BLENDER_MCP_BLENDER_BINARY."; exit 1; fi; \
	echo "Using Blender binary: $$blender_bin"; \
	BLENDER_MCP_BLENDER_BINARY="$$blender_bin" BLENDER_MCP_WORKSPACE_ROOTS=workspace $(PYTHON) -m pytest tests/test_bridge_attach.py::test_bridge_can_start_blender_runtime_and_report_runtime_info -q

package-check:
	rm -rf dist build
	$(PYTHON) -m build --sdist --wheel
	$(PYTHON) tests/package_smoke.py --dist-dir dist

schema-export:
	$(PYTHON) -m mcp_server.schema_tools export

schema-check:
	$(PYTHON) -m mcp_server.schema_tools check

run-stdio:
	$(PYTHON) -m mcp_server.main --transport stdio

run-http-unsafe:
	BLENDER_MCP_ENABLE_UNAUTHENTICATED_HTTP=true $(PYTHON) -m mcp_server.main --transport http

controller-smoke:
	$(PYTHON) -m blender_controller.smoke
