using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace QBDesktopReader
{
    public class Encryption
    {
        public class EncryptionResult
        {
            public byte[] EncryptedData { get; set; }
            public byte[] Key { get; set; }
            public byte[] IV { get; set; }
            public byte[] Tag { get; set; }
        }

        /// <summary>
        /// Encrypt data using AES-256-GCM (authenticated encryption)
        /// </summary>
        public static EncryptionResult EncryptAES256GCM(byte[] plaintext)
        {
            // Generate random 256-bit key
            byte[] key = new byte[32]; // 256 bits
            using (var rng = new RNGCryptoServiceProvider())
            {
                rng.GetBytes(key);
            }

            // Generate random 96-bit IV (nonce)
            byte[] iv = new byte[12]; // 96 bits for GCM
            using (var rng = new RNGCryptoServiceProvider())
            {
                rng.GetBytes(iv);
            }

            // Encrypt using AES-GCM
            byte[] ciphertext;
            byte[] tag;

            using (var aes = new AesGcm(key))
            {
                ciphertext = new byte[plaintext.Length];
                tag = new byte[16]; // 128-bit authentication tag

                aes.Encrypt(iv, plaintext, ciphertext, tag);
            }

            return new EncryptionResult
            {
                EncryptedData = ciphertext,
                Key = key,
                IV = iv,
                Tag = tag
            };
        }

        /// <summary>
        /// Decrypt data using AES-256-GCM
        /// </summary>
        public static byte[] DecryptAES256GCM(byte[] ciphertext, byte[] key, byte[] iv, byte[] tag)
        {
            byte[] plaintext = new byte[ciphertext.Length];

            using (var aes = new AesGcm(key))
            {