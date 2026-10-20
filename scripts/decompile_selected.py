# -*- coding: utf-8 -*-
"""Ghidra post-script: decompile a list of function entry addresses.

Usage:
  analyzeHeadless <projdir> cc700pro -process cc700pro_app.elf -noanalysis \
      -postScript decompile_selected.py <addresses_file>
Arguments:
  addresses_file: text file, one 0x-prefixed address per line (# comments ok)
"""
import os

args = list(getScriptArgs())
if not args:
    print("ERROR: pass addresses file as script argument")
    raise SystemExit(1)

path = args[0]
with open(path, "r", encoding="utf-8") as fh:
    raw = [ln.strip() for ln in fh if ln.strip() and not ln.strip().startswith("#")]

try:
    mon = monitor
except NameError:
    mon = None

from ghidra.app.decompiler import DecompInterface

dec = DecompInterface()
dec.openProgram(currentProgram)
af = currentProgram.getAddressFactory().getDefaultAddressSpace()

for a in raw:
    addr = af.getAddress(a)
    fn = getFunctionAt(addr)
    if fn is None:
        fn = getFunctionContaining(addr)
    if fn is None:
        print("===FUNC %s NOT-FOUND===" % a)
        continue
    res = dec.decompileFunction(fn, 90, mon)
    print("===FUNC %s %s %s===" % (a, fn.getName(), str(fn.getEntryPoint())))
    if res and res.getDecompiledFunction():
        print(res.getDecompiledFunction().getC())
    else:
        print("(decompile failed: %s)" % (res.getErrorMessage() if res else "no result"))
    print("===END %s===" % a)
