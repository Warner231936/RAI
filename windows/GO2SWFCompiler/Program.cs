using GalaxyOrbit.Resources;
using System.Diagnostics.CodeAnalysis;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace GO2SWFCompiler
{
    internal class Program
    {
        [DllImport("msvcrt.dll", CallingConvention = CallingConvention.Cdecl)]
        static extern int memcmp(byte[] b1, byte[] b2, long count);
        [RequiresUnreferencedCode("Calls System.Text.Json.JsonSerializer.Serialize<TValue>(TValue, JsonSerializerOptions)")]
        [RequiresDynamicCode("Calls System.Text.Json.JsonSerializer.Serialize<TValue>(TValue, JsonSerializerOptions)")]
        static void Main(string[] args)
        {
            if(args.Length == 0 || (args.Length > 0 && args[0] == "-e"))
            {
#if DEBUG
                List<FileVersion> files = new List<FileVersion>();
                foreach (var file in Directory.GetFiles("client", "*.*", SearchOption.AllDirectories))
                {
                    if (file.EndsWith("backup.swf"))
                    {
                        continue;
                    }
                    var bytes = File.ReadAllBytes(file);
                    var encrypted = new byte[] { };
                    var decrypted = new byte[] { };
                    string hash = null;
                    switch (file.Split(".").Last().ToLower())
                    {
                        case "swf":
                            encrypted = GO2Compression.SecureCompress(bytes, GO2Compression.EncryptionType.bngo2, out hash);
                            break;
                        case "js":
                            encrypted = GO2Compression.SecureCompress(bytes, GO2Compression.EncryptionType.jsgo2, out hash);
                            break;
                        case "mp3":
                            encrypted = GO2Compression.SecureCompress(bytes, GO2Compression.EncryptionType.mpgo2, out hash);
                            break;
                        case "jpg":
                            encrypted = GO2Compression.SecureCompress(bytes, GO2Compression.EncryptionType.imgo2, out hash);
                            break;
                        case "xml":
                            encrypted = GO2Compression.SecureCompress(bytes, GO2Compression.EncryptionType.xmgo2, out hash);
                            break;
                    }
                    var fileName = file.Substring(0, file.LastIndexOf("."));
                    fileName = fileName.Replace("client\\", "gamedata\\");
                    files.Add(new FileVersion
                    {
                        FileName = fileName.ToLower(),
                        Hash = hash
                    });
                    //try decompile
                    decrypted = GO2Compression.SecureDecompress(encrypted, GO2Compression.ParseHeader(encrypted));
                    if (!ByteArrayCompare(decrypted, bytes))
                    {
                        throw new InvalidDataException("Decrypt unsuccess");
                    }
                    //success
                    Console.WriteLine("[Compressed]: " + file);
                    File.WriteAllBytes(file.Substring(0, file.LastIndexOf(".")) + ".go2", encrypted);
                }
                File.WriteAllText("gamedata.json", JsonSerializer.Serialize(files), Encoding.UTF8);
                foreach (var file in Directory.GetFiles("client", "*.*", SearchOption.AllDirectories))
                {
                    if (!file.EndsWith("go2"))
                    {
                        continue;
                    }
                    var path = file.Replace("client\\", "gamedata\\");
                    path = path.Substring(0, path.LastIndexOf("\\"));
                    if (!Directory.Exists(path))
                    {
                        Directory.CreateDirectory(path);
                    }
                    if (File.Exists(file.Replace("client\\", "gamedata\\")))
                    {
                        File.Delete(file.Replace("client\\", "gamedata\\"));
                    }
                    File.Move(file, file.Replace("client\\", "gamedata\\").ToLower());
                }
#endif
            }
            else if(args.Length > 0 && args[0] == "-d")
            {
                if (!Directory.Exists("gamedata"))
                {
                    Directory.CreateDirectory("gamedata");
                }
                foreach (var file in Directory.GetFiles("gamedata", "*.*", SearchOption.AllDirectories))
                {
                    if (!file.EndsWith(".go2"))
                    {
                        continue;
                    }
                    var path = file.Replace("gamedata\\", "client\\");
                    path = path.Substring(0, path.LastIndexOf("\\"));
                    if (!Directory.Exists(path))
                    {
                        Directory.CreateDirectory(path);
                    }
                    if (File.Exists(file.Replace("gamedata\\", "client\\")))
                    {
                        File.Delete(file.Replace("gamedata\\", "client\\"));
                    }
                    var bytes = File.ReadAllBytes(file);
                    //try decompile
                    var header = GO2Compression.ParseHeader(bytes);
                    var decompressed = GO2Compression.SecureDecompress(bytes, header);

                    Console.WriteLine("[Decompressed]: " + file);
                    var xpath = file.Replace("gamedata\\", "client\\");
                    switch (header)
                    {
                        case GO2Compression.EncryptionType.bngo2:
                            File.WriteAllBytes(xpath.Substring(0, xpath.LastIndexOf(".")) + ".swf", decompressed);
                            break;
                        case GO2Compression.EncryptionType.imgo2:
                            File.WriteAllBytes(xpath.Substring(0, xpath.LastIndexOf(".")) + ".jpg", decompressed);
                            break;
                        case GO2Compression.EncryptionType.mpgo2:
                            File.WriteAllBytes(xpath.Substring(0, xpath.LastIndexOf(".")) + ".mp3", decompressed);
                            break;
                        case GO2Compression.EncryptionType.jsgo2:
                            File.WriteAllBytes(xpath.Substring(0, xpath.LastIndexOf(".")) + ".js", decompressed);
                            break;
                        case GO2Compression.EncryptionType.xmgo2:
                            File.WriteAllBytes(xpath.Substring(0, xpath.LastIndexOf(".")) + ".xml", decompressed);
                            break;
                    }
                }
            }
        }
        private static bool ByteArrayCompare(byte[] b1, byte[] b2)
        {
            // Validate buffers are the same length.
            // This also ensures that the count does not exceed the length of either buffer.  
            return b1.Length == b2.Length && memcmp(b1, b2, b1.Length) == 0;
        }
    }
}
