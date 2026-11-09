BUILD_DIR := build
GAME_DSK := $(BUILD_DIR)/elite.dsk
PLAY_DSK ?= saves/elite.dsk

.PHONY: build run shot verify extract extract-legend legend toolchain clean docs docs-capture

# Native RT-11 SAV/DAT files, installed on a bootable RT-11 floppy.
build:
	python3 tools/build_elite.py $(GAME_DSK) --force

# build, then open a playable emulator window (SDL2, UKNCBTL core)
run: build
	python3 tools/play_disk.py $(GAME_DSK) $(PLAY_DSK) --manifest $(BUILD_DIR)/manifest.json
	bin/ukncbtl/uknc-play --rom bin/ukncbtl/uknc_rom.bin --disk $(PLAY_DSK)

# headless proof-of-life: boot, screenshot what is on screen
shot: build
	python3 tools/uknc_control.py boot --disk $(GAME_DSK) \
	    --wait 400 --shot tmp/run-shot.png

# Full host-resource and headless-emulator regression suite
verify: build
	python3 -u tools/verify_build.py

# Re-extract Russian world vocabulary from the original Spectrum disk.
# This overwrites maintained text resources; review the result before keeping it.
extract:
	python3 tools/planet_extract.py --out src/res/text/planet.txt --force

# re-extract the Legend resources from orig/legend (destructive): every
# hull with every header, the tables, and the Russian text
extract-legend:
	python3 tools/legend_ships.py --force
	python3 tools/legend_tables.py --force
	python3 tools/legend_text.py --force

# build Elite Legend itself from its sources (wine + the author's
# sjasmplus) and run the snapshot in ZEsarUX: the reference machine
legend:
	python3 tools/legend_build.py --run --shot tmp/legend-title.png

# rebuild macro11 and the emulators from source into bin/
toolchain:
	python3 tools/build_toolchain.py

clean:
	rm -rf $(BUILD_DIR)

# Offline player documentation from maintained text and captured screens.
docs:
	python3 tools/manual_pdf.py
	python3 tools/control_pdf.py --board uknc
	python3 tools/control_pdf.py --board pc

# Capture real current-build screens on a disposable disk before publishing docs.
docs-capture: build
	python3 tools/manual_pdf.py --capture
	python3 tools/control_pdf.py --board uknc
	python3 tools/control_pdf.py --board pc
