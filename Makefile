# Makefile for compiling Python files to .mpy files using mpy-cross

# Path to mpy-cross executable
MPY_CROSS = mpy-cross

# Define build directories
BUILD_DIR = build
SATKIT_BUILD_DIR = $(BUILD_DIR)/satkit
GS_BUILD_DIR = $(BUILD_DIR)/gs

# Additional Python files to compile (can be set from command line)
# Example: make EXTRA_PY_FILES="foo.py bar/baz.py"
EXTRA_PY_FILES ?=
EXTRA_MPY_FILES := $(patsubst %.py,$(BUILD_DIR)/%.mpy,$(EXTRA_PY_FILES))

# Extra files to include with satkit
EXTRA_SATKIT_FILES ?=
EXTRA_SATKIT_MPY_FILES := $(patsubst %.py,$(SATKIT_BUILD_DIR)/%.mpy,$(EXTRA_SATKIT_FILES))

# Extra files to include with gs
EXTRA_GS_FILES ?=
EXTRA_GS_MPY_FILES := $(patsubst %.py,$(GS_BUILD_DIR)/%.mpy,$(EXTRA_GS_FILES))

# Python source directories
SRC_DIRS = manha

# Find all Python files in source directories
PY_FILES := $(shell find $(SRC_DIRS) -name "*.py")
# Generate corresponding .mpy file paths in build directory
MPY_FILES := $(patsubst %.py,$(BUILD_DIR)/%.mpy,$(PY_FILES)) $(EXTRA_MPY_FILES)

# Files needed for satkit
SATKIT_DEPS := $(shell find manha/satkit -name "*.py") \
               $(shell find manha/internals -name "*.py") \
               manha/__init__.py

# Files needed for gs
GS_DEPS := $(shell find manha/gs -name "*.py") \
           $(shell find manha/internals -name "*.py") \
           manha/__init__.py

# Generate output paths for satkit
SATKIT_MPY_FILES := $(patsubst manha/%.py,$(SATKIT_BUILD_DIR)/%.mpy,$(SATKIT_DEPS)) $(EXTRA_SATKIT_MPY_FILES)

# Generate output paths for gs
GS_MPY_FILES := $(patsubst manha/%.py,$(GS_BUILD_DIR)/%.mpy,$(GS_DEPS)) $(EXTRA_GS_MPY_FILES)

# Default target
all: build

# Build target
build: $(MPY_FILES)

# Satkit-specific build target
satkit: clean_satkit $(SATKIT_MPY_FILES)
	mkdir -p $(SATKIT_BUILD_DIR)/manha 
	find $(SATKIT_BUILD_DIR) -maxdepth 1 -not -name manha -a -not -path $(SATKIT_BUILD_DIR) -exec mv {} $(SATKIT_BUILD_DIR)/manha \;

# GS-specific build target
gs: clean_gs $(GS_MPY_FILES)
	mkdir -p $(GS_BUILD_DIR)/manha
	find $(GS_BUILD_DIR) -maxdepth 1 -not -name manha -a -not -path $(GS_BUILD_DIR) -exec mv {} $(GS_BUILD_DIR)/manha \;

# Rule to create .mpy files from .py files for full build
$(BUILD_DIR)/%.mpy: %.py
	@mkdir -p $(dir $@)
	$(MPY_CROSS) -o $@ $<

# Rule for satkit-specific files
$(SATKIT_BUILD_DIR)/%.mpy: manha/%.py
	@mkdir -p $(dir $@)
	$(MPY_CROSS) -o $@ $<

$(SATKIT_BUILD_DIR)/%.mpy: %.py
	@mkdir -p $(dir $@)
	$(MPY_CROSS) -o $@ $<

# Rule for gs-specific files
$(GS_BUILD_DIR)/%.mpy: manha/%.py
	@mkdir -p $(dir $@)
	$(MPY_CROSS) -o $@ $<

$(GS_BUILD_DIR)/%.mpy: %.py
	@mkdir -p $(dir $@)
	$(MPY_CROSS) -o $@ $<

clean_gs:
	rm -rf $(GS_BUILD_DIR)

clean_satkit:
	rm -rf $(SATKIT_BUILD_DIR)

# Clean target
clean:
	rm -rf $(BUILD_DIR)

# Create build directories
$(BUILD_DIR) $(SATKIT_BUILD_DIR) $(GS_BUILD_DIR):
	mkdir -p $@

.PHONY: all build clean satkit gs