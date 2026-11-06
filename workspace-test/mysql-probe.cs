// Qualification against the exact legacy client's Connector/NET assembly.
using System;
using System.IO;
using MySql.Data.MySqlClient;
public class Probe {
  public static int Main() {
    Console.WriteLine("Connector/NET: "+typeof(MySqlConnection).Assembly.GetName().Version);
    var password=File.ReadAllText("/run/ws-test/backend-password").Trim();
    var failed=false;
    foreach (var charset in new [] {"utf8", "utf8mb4"}) {
      try {
        using(var connection=new MySqlConnection("Server=database;Database=onlyoffice_mailserver;User ID=oo_admin;Password="+password+";SSL Mode=None;Character Set="+charset+";Connection Timeout=5;")) {
          connection.Open();
          using(var command=new MySqlCommand("SELECT COUNT(*) FROM domain",connection))
            Console.WriteLine(charset+": connected; domains="+command.ExecuteScalar());
        }
      } catch(Exception error) {failed=true;Console.WriteLine(charset+": "+error.GetType().FullName+": "+error.Message);}
    }
    return failed?1:0;
  }
}
