// Assemble the Di2 page-turn hook that sends the GUI page message directly.
// Cave layout:
//   0x422f4d1c: u32 FUN_420f65b4 (GUI message send)
//   0x422f4d20: unused/reserved
//   0x422f4d24: code
import ghidra.app.plugin.assembler.Assembler;
import ghidra.app.plugin.assembler.Assemblers;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;

public class AssembleHookGui extends GhidraScript {
	private String hex(byte[] b) {
		StringBuilder sb = new StringBuilder();
		for (byte x : b) sb.append(String.format("%02x", x & 0xff));
		return sb.toString();
	}

	@Override
	public void run() throws Exception {
		Address at = currentProgram.getAddressFactory().getAddress("0x422f4d24");
		Assembler asm = Assemblers.getAssembler(currentProgram);
		String[] lines = {
			"entry a1, 0x30",
			"movi a10, 0x99",
			"movi a11, 0x4b",
			"movi a8, 0xe",
			"sub a8, a2, a8",
			"movi a12, 3",
			"bgeu a8, a12, 0x422f4d54",
			"moveqz a10, a11, a8",
			"s32i a10, a1, 0x14",
			"movi a8, 0",
			"s32i a8, a1, 0x10",
			"s32i a8, a1, 0x18",
			"s32i a8, a1, 0x1c",
			// FUN_420f65b4 param_1 is caller a10 (callee a2) in the windowed ABI.
			"addi a10, a1, 0x10",
			"l32r a8, 0x422f4d1c",
			"callx8 a8",
			"retw.n"
		};
		StringBuilder all = new StringBuilder();
		for (String line : lines) {
			try {
				byte[] bytes = asm.assembleLine(at, line);
				println(String.format("%08x", at.getOffset()) + "  " + line + "  -> " + hex(bytes));
				all.append(hex(bytes));
				at = at.add(bytes.length);
			}
			catch (Exception e) {
				println("FAIL 0x" + Long.toHexString(at.getOffset()) + "  " + line + " -> " + e);
			}
		}
		println("HOOK_HEX=" + all);
		println("HOOK_LEN=" + (all.length() / 2));
		println("HOOK_END=0x" + Long.toHexString(at.getOffset()));
		println("ASSEMBLE_HOOK_GUI_DONE");
	}
}
