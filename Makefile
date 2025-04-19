# Makefile for compiling Python files to .mpy files using mpy-cross

# Path to mpy-cross executable
MPY_CROSS = mpy-cross

# Define build directory
BUILD_DIR = build

# Additional Python files to compile (can be set from command line)
# Example: make EXTRA_PY_FILES="foo.py bar/baz.py"
EXTRA_PY_FILES ?=
EXTRA_MPY_FILES := $(patsubst %.py,$(BUILD_DIR)/%.mpy,$(EXTRA_PY_FILES))

# Python source directories
SRC_DIRS = manha

# Find all Python files in source directories
PY_FILES := $(shell find $(SRC_DIRS) -name "*.py")
# Generate corresponding .mpy file paths in build directory
MPY_FILES := $(patsubst %.py,$(BUILD_DIR)/%.mpy,$(PY_FILES)) $(EXTRA_MPY_FILES)

# Default target
all: build

# Build target
build: $(MPY_FILES)

# Rule to create .mpy files from .py files for full build
$(BUILD_DIR)/%.mpy: %.py
	@mkdir -p $(dir $@)
	$(MPY_CROSS) -o $@ $<

# Clean target
clean:
	rm -rf $(BUILD_DIR)

# Create build directory
$(BUILD_DIR):
	mkdir -p $@

.PHONY: all build clean