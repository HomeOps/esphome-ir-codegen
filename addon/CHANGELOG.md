# Changelog

## [0.4.0](https://github.com/HomeOps/esphome-ir-codegen/compare/v0.3.0...v0.4.0) (2026-06-17)


### ⚠ BREAKING CHANGES

* generated button ids use the canonical control as the key (e.g. ..._power -> ..._power_toggle, ..._vol_up -> ..._volume_up); update any button.press references accordingly.

### Features

* depend on homeops-ir-adapter + homeops-ir-canonical ([#21](https://github.com/HomeOps/esphome-ir-codegen/issues/21)) ([013ee60](https://github.com/HomeOps/esphome-ir-codegen/commit/013ee607403ab5aa2644a27984a8c0f9091779bf))

## [0.3.0](https://github.com/HomeOps/esphome-ir-codegen/compare/v0.2.1...v0.3.0) (2026-06-17)


### ⚠ BREAKING CHANGES

* per-device repo+ref built on demand; path-namespaced button ids ([#19](https://github.com/HomeOps/esphome-ir-codegen/issues/19))

### Features

* per-device repo+ref built on demand; path-namespaced button ids ([#19](https://github.com/HomeOps/esphome-ir-codegen/issues/19)) ([2036311](https://github.com/HomeOps/esphome-ir-codegen/commit/2036311e3c9f4aa377f576123c818f2a58793061))

## [0.2.1](https://github.com/HomeOps/esphome-ir-codegen/compare/v0.2.0...v0.2.1) (2026-06-15)


### Bug Fixes

* **addon:** put the changelog where Home Assistant looks for it ([#14](https://github.com/HomeOps/esphome-ir-codegen/issues/14)) ([e9be74c](https://github.com/HomeOps/esphome-ir-codegen/commit/e9be74c51d3f602f0051eb83623172df7f172114))

## [0.2.0](https://github.com/HomeOps/esphome-ir-codegen/compare/v0.1.2...v0.2.0) (2026-06-15)


### ⚠ BREAKING CHANGES

* the flipper adapter is served as `flipper.git`, not `default.git`. Devices must update `packages: url:` accordingly.

### Features

* serve multiple source adapters (flipper + ha-ir) ([#11](https://github.com/HomeOps/esphome-ir-codegen/issues/11)) ([a802de8](https://github.com/HomeOps/esphome-ir-codegen/commit/a802de80278680025d760422f209daee6b63f0a6))

## [0.1.2](https://github.com/HomeOps/esphome-ir-codegen/compare/v0.1.1...v0.1.2) (2026-06-15)


### Features

* encode all parsed protocols via the infrared-protocols library ([#9](https://github.com/HomeOps/esphome-ir-codegen/issues/9)) ([fdfb263](https://github.com/HomeOps/esphome-ir-codegen/commit/fdfb26332e8e2031024ebe49c48f25f0f99c10fb))

## [0.1.1](https://github.com/HomeOps/esphome-ir-codegen/compare/v0.1.0...v0.1.1) (2026-06-15)


### Features

* path-less add-on (one repo param) serving the whole DB as default.git ([#5](https://github.com/HomeOps/esphome-ir-codegen/issues/5)) ([aba40f5](https://github.com/HomeOps/esphome-ir-codegen/commit/aba40f5ea1377b9e16ec367f7452fe58ab896400))

## 0.1.0 (2026-06-15)


### Features

* dockerized codegen + Sony Bravia end-to-end CI ([#1](https://github.com/HomeOps/esphome-ir-codegen/issues/1)) ([5e83655](https://github.com/HomeOps/esphome-ir-codegen/commit/5e83655860b0069d3ad3da3a70949aaa7fe2d185))
* initial Flipper-IRDB -&gt; ESPHome codegen prototype ([16f2b75](https://github.com/HomeOps/esphome-ir-codegen/commit/16f2b759dca45fac461ec4f5398d50842575a3ef))


### Miscellaneous Chores

* release 0.1.0 ([89bd65c](https://github.com/HomeOps/esphome-ir-codegen/commit/89bd65cbdd00f849c1a8cf0e5e4a76f1532e3d7a))

## Changes

All notable changes to this project are recorded here.

This file is maintained automatically by
[release-please](https://github.com/googleapis/release-please) from
[Conventional Commit](https://www.conventionalcommits.org/) messages; a new
versioned section is added each time a release PR is merged.
