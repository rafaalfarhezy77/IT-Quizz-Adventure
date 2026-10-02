/* New original practice content, independent of the Flask and competition banks. */
(function(root){
  'use strict';
  const q=(id,text,options,key,explanation,stage=1,accepted=[])=>({id,text,options,key,explanation,stage,accepted,weight:stage===3?6:10});
  const packs={
    cyber:{slug:'cyber',title:'Cyber Security',method:'quiz',version:'pages-cyber-v1',duration:240,members:1,bonusPerSecond:1,questions:[
      q(1,'Anda menerima kode login yang tidak pernah diminta. Apa tindakan yang tepat?',['Berikan kode kepada penelepon','Periksa aktivitas akun melalui aplikasi resmi dan amankan akun','Unggah kode ke grup kelas','Abaikan semua notifikasi selamanya'],'B','Kode login tidak boleh dibagikan. Periksa aktivitas melalui kanal resmi dan ikuti langkah pengamanan akun.'),
      q(2,'Mengapa akun pengelola sebaiknya berbeda dari akun untuk aktivitas sehari-hari?',['Agar tugas biasa tidak selalu memakai hak akses tinggi','Agar semua orang memakai kata sandi yang sama','Agar pencatatan tidak diperlukan','Agar pembaruan keamanan dihindari'],'A','Pemisahan akun membatasi penggunaan hak istimewa dan mengurangi dampak kesalahan pada aktivitas biasa.'),
      q(3,'Apa yang perlu dilakukan sebelum membagikan tangkapan layar pengaturan akun?',['Tampilkan seluruh kode pemulihan','Tampilkan alamat semua anggota','Samarkan token, kode pemulihan, dan data pribadi yang tidak diperlukan','Matikan pengunci layar'],'C','Data rahasia dan identitas yang tidak diperlukan harus disamarkan sebelum tangkapan layar dibagikan.'),
      q(4,'Bagaimana memastikan cadangan data benar-benar dapat digunakan?',['Hanya menghitung nama file','Menghapus data asli setiap hari','Menyimpan satu salinan pada perangkat yang sama saja','Menguji pemulihan data secara berkala'],'D','Uji pemulihan memeriksa bahwa cadangan dapat dibaca dan mengembalikan data yang dibutuhkan.'),
      q(5,'Pembaruan keamanan tersedia untuk browser. Langkah yang tepat?',['Pasang melalui mekanisme pembaruan resmi','Cari pemasang dari pesan acak','Matikan pembaruan selamanya','Bagikan kata sandi agar orang lain memasangnya'],'A','Pembaruan resmi memperbaiki masalah keamanan dan menjaga integritas perangkat lunak.'),
      q(6,'Anda menemukan dokumen internal terbuka untuk publik. Apa respons yang tepat?',['Sebarkan tautannya ke semua orang','Laporkan ke pengelola melalui kanal resmi tanpa menyebarkan isinya','Ubah seluruh dokumen','Unduh dan publikasikan ulang'],'B','Pelaporan terbatas kepada pengelola membantu penanganan tanpa memperluas paparan data.')
    ]},
    networking:{slug:'networking',title:'Networking',method:'networking',version:'pages-networking-v1',duration:300,members:1,bonusPerSecond:1,stageSeconds:[90,60,150],stageNames:['Signal Check','True or Trap','Case Signal'],questions:[
      q(1,'Perangkat penghubung antarjaringan IP disebut apa?',['Monitor','Hub USB','Router','Keyboard','Scanner'],'C','Router meneruskan paket antarjaringan IP.'),
      q(2,'Protokol apa yang umum digunakan untuk sinkronisasi waktu perangkat?',['NTP','SMTP','POP3','FTP','ARP'],'A','NTP digunakan untuk menyinkronkan waktu perangkat pada jaringan.'),
      q(3,'Alat apa yang paling relevan untuk memeriksa susunan koneksi kabel Ethernet?',['Speaker','Cable tester','Proyektor','Webcam','Printer'],'B','Cable tester membantu memeriksa kontinuitas dan susunan sambungan kabel.'),
      q(4,'Alamat 127.0.0.1 pada IPv4 menunjuk ke perangkat itu sendiri.',['Benar','Salah'],'A','Alamat loopback digunakan untuk komunikasi lokal pada perangkat yang sama.',2),
      q(5,'Dua perangkat boleh selalu menggunakan alamat IPv4 yang sama dalam satu subnet.',['Benar','Salah'],'B','Alamat duplikat pada satu subnet dapat menimbulkan konflik.',2),
      q(6,'VLAN dapat memisahkan domain broadcast secara logis.',['Benar','Salah'],'A','VLAN membagi jaringan layer 2 ke domain broadcast yang terpisah.',2),
      q(7,'Kabel jaringan yang terlepas tetap dapat membawa data Ethernet secara normal.',['Benar','Salah'],'B','Koneksi fisik harus tersedia agar jalur Ethernet kabel dapat bekerja.',2),
      q(8,'Nama perangkat yang meneruskan paket dari LAN ke jaringan lain?',[],'router','Router menghubungkan jaringan IP yang berbeda.',3,['perute','network router']),
      q(9,'Nama protokol untuk menyinkronkan jam perangkat jaringan?',[],'NTP','Network Time Protocol membantu sinkronisasi waktu.',3,['network time protocol']),
      q(10,'Sebutkan alamat IPv4 loopback yang umum dipakai untuk memeriksa perangkat sendiri.',[],'127.0.0.1','127.0.0.1 merupakan alamat loopback IPv4.',3),
      q(11,'Singkatan teknologi pemisahan LAN menjadi domain broadcast logis?',[],'VLAN','Virtual LAN memisahkan jaringan layer 2 secara logis.',3,['virtual lan','virtual local area network']),
      q(12,'Nama alat untuk memeriksa kontinuitas sambungan kabel Ethernet?',[],'cable tester','Cable tester membantu pemeriksaan jalur kabel dan urutan sambungannya.',3,['network cable tester','tester kabel','penguji kabel'])
    ]},
    hardware:{slug:'hardware',title:'Hardware',method:'hardware',version:'pages-hardware-v1',duration:300,members:1,questions:[],caseTitle:'Komputer studio podcast sekolah',caseText:'Studio podcast sekolah memerlukan komputer untuk menyunting audio dan video ringan. Susun rakitan dengan budget latihan USD 1400, target CPU 1100 dan GPU 1900. Pilih enam komponen yang sesuai dan tulis alasan singkat. Seluruh harga, nama, dan performa merupakan data sintetis latihan.',rules:{budget:1400,cpu:1100,gpu:1900,efficiency:2},catalogue:{
      cpu:[{id:'cpu-a',name:'CPU Simulasi A',price:210,score:1300,watts:70,socket:'S1'},{id:'cpu-b',name:'CPU Simulasi B',price:350,score:2000,watts:110,socket:'S2'},{id:'cpu-c',name:'CPU Simulasi C',price:140,score:800,watts:45,socket:'S1'}],
      motherboard:[{id:'board-a',name:'Board Simulasi A',price:125,socket:'S1',ram:'DDR4'},{id:'board-b',name:'Board Simulasi B',price:200,socket:'S2',ram:'DDR5'},{id:'board-c',name:'Board Simulasi C',price:155,socket:'S1',ram:'DDR5'}],
      gpu:[{id:'gpu-a',name:'GPU Simulasi A',price:280,score:2100,watts:140},{id:'gpu-b',name:'GPU Simulasi B',price:600,score:3600,watts:300},{id:'gpu-c',name:'GPU Simulasi C',price:180,score:1300,watts:90}],
      ram:[{id:'ram-a',name:'RAM Simulasi A',price:65,capacity:16,ram:'DDR4'},{id:'ram-b',name:'RAM Simulasi B',price:115,capacity:32,ram:'DDR5'},{id:'ram-c',name:'RAM Simulasi C',price:40,capacity:8,ram:'DDR4'}],
      storage:[{id:'storage-a',name:'SSD Simulasi A',price:85,capacity:1000},{id:'storage-b',name:'SSD Simulasi B',price:55,capacity:500},{id:'storage-c',name:'SSD Simulasi C',price:130,capacity:2000}],
      psu:[{id:'psu-a',name:'PSU Simulasi A',price:75,watts:450},{id:'psu-b',name:'PSU Simulasi B',price:110,watts:700},{id:'psu-c',name:'PSU Simulasi C',price:45,watts:250}]
    }}
  };
  root.DemoPacks=packs;
  if(typeof module!=='undefined')module.exports=packs;
}(globalThis));
