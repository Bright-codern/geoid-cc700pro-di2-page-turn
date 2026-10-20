// Decode arbitrary bytes with Ghidra's Xtensa disassembler without modifying the program.
// Usage: -postScript PseudoDisasm.java <base-address> <hex-bytes>
import ghidra.app.script.GhidraScript;
import ghidra.app.util.PseudoDisassembler;
import ghidra.app.util.PseudoInstruction;
import ghidra.program.model.address.Address;

public class PseudoDisasm extends GhidraScript {
	@Override
	public void run() throws Exception {
		String[] args = getScriptArgs();
		if (args.length < 2) {
			println("usage: PseudoDisasm.java <base-address> <hex-bytes>");
			return;
		}
		Address base = currentProgram.getAddressFactory().getAddress(args[0]);
		String hs = args[1].replaceAll("\\s+", "");
		byte[] all = new byte[hs.length() / 2];
		for (int i = 0; i < all.length; i++) {
			all[i] = (byte) Integer.parseInt(hs.substring(i * 2, i * 2 + 2), 16);
		}
		PseudoDisassembler pd = new PseudoDisassembler(currentProgram);
		int off = 0;
		while (off < all.length) {
			byte[] rest = new byte[all.length - off];
			System.arraycopy(all, off, rest, 0, rest.length);
			Address a = base.add(off);
			try {
				PseudoInstruction pi = pd.disassemble(a, rest);
				int len = pi.getParsedLength();
				println(String.format("%08x  %-24s  %s", a.getOffset(),
					hs.substring(off * 2, Math.min(hs.length(), (off + len) * 2)), pi.toString()));
				off += len;
			}
			catch (Exception e) {
				println(String.format("%08x  <decode failed: %s>", a.getOffset(), e));
				off++;
			}
		}
		println("PSEUDO_DISASM_DONE");
	}
}
