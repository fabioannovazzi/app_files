function derLength(length) {
  if (length < 128) return Buffer.from([length]);
  const bytes = [];
  for (let value = length; value > 0; value = Math.floor(value / 256)) bytes.unshift(value & 0xff);
  return Buffer.from([0x80 | bytes.length, ...bytes]);
}

function tlv(tag, ...values) {
  const content = Buffer.concat(values.map((value) => Buffer.from(value)));
  return Buffer.concat([Buffer.from([tag]), derLength(content.length), content]);
}

export function syntheticSignedP7m(xml) {
  const signedDataOid = tlv(0x06, Buffer.from("2a864886f70d010702", "hex"));
  const dataOid = tlv(0x06, Buffer.from("2a864886f70d010701", "hex"));
  const encapsulated = tlv(0x30, dataOid, tlv(0xa0, tlv(0x04, xml)));
  const signedData = tlv(0x30, tlv(0x02, Buffer.from([1])), tlv(0x31), encapsulated);
  return tlv(0x30, signedDataOid, tlv(0xa0, signedData));
}

