namespace BizHawk.Emulation.Cores.Components.H6280;

public sealed partial class HuC6280
{
	private readonly byte[] _memory = new byte[0x10000];

	public void Load(ushort address, ReadOnlySpan<byte> data) => data.CopyTo(_memory.AsSpan(address));

	public byte ReadMemory(ushort address) => _memory[address];

	public ushort ReadWord(ushort address)
	{
		var low = ReadMemory(address);
		var high = ReadMemory(unchecked((ushort) (address + 1)));
		return (ushort) (low | (high << 8));
	}
}
