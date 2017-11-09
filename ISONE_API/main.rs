#![feature(plugin)]
// #![plugin(docopt_macros)]
extern crate hyper;
extern crate rustc_serialize;
extern crate url;
extern crate docopt;
extern crate serde_json;
extern crate zmq;
//extern crate hyper_auth;


//use serialize::{json};
use std::collections::HashMap;

use std::env;
use std::thread;
use std::io::Read;

use rustc_serialize::{Encodable, json, Decodable, Decoder};
use url::form_urlencoded;
use docopt::Docopt;
use hyper::header::{Headers, Authorization, Basic,Accept,qitem};
use hyper::client::Client;
use hyper::mime::{Mime, TopLevel, SubLevel};

use serde_json::Value;
use zmq::{Context, Message, Error};

/*
TODO: 

x 1. shared Headers structure rather than cloned. 
  WONTFIX: headers needs to be mutable and thus cloned.
--- 
2. serde parsing and repacking. 
---

Parsing is done. Repacking can be done at any time..

x. 3. ZMQ

Includes the library just fine. 
Posts to a topic. 

4. Make it a daemon with a timed re-query.
*/

const USAGE: &'static str = "
Usage: myproject <resource> ...

Options:
    --baseurl=<baseurl>  # Base URL  [default: https://webservices.iso-ne.com/api/v1.1/].
    --password=<password>  # Password [default: VolttronShines].
    --username=<username>  # Username [default: ocschwar@mit.edu].
";

#[derive(Debug, RustcDecodable)]
struct Args {
    arg_resource: Vec<String>,
    flag_baseurl: String,
    flag_username: String,
    flag_password: String,
}

fn get_content(url: &String, headers: Headers) -> hyper::Result<String> {
    let client = Client::new();    
    let mut response = match
        client.get(url).headers(headers).send() {
            Ok(response) => response,
            Err(e) => {
                println!("{:?}",e);
                panic!("Whoops.")
            }
        };

    let mut buf = String::new();
    try!(response.read_to_string(&mut buf));
    Ok(buf)
}

fn main() {

    let args: Args = Docopt::new(USAGE)
        .and_then(|d| d.decode())
        .unwrap_or_else(|e| {println!("DAMN {:?}",e); e.exit()});
    println!("{:?}", args);
    
    let mut headers = Headers::new();
    headers.set(
        Authorization(
            Basic {
                username: args.flag_username,
                password: Some(args.flag_password)
            }
        ));
    headers.set(
        Accept(vec![
            qitem(Mime(TopLevel::Application, SubLevel::Json, vec![])),
        ]));
    // Use a reference to
    // keep hte mutable variable out of the scope of the for loop.
    //
    // That reference needs to be used for a clone because the
    // Hyper HTTP client does mutate the Headers object it gets
    // (to set the Hostname header as per HTTP 1.1)
    let r = & headers;
    
    let mut joins = vec![];
    let mut ctx = Context::new();
    let addr = "tcp://127.0.0.1:25933";
    let mut sock = match ctx.socket(zmq::PUB) {
        Ok(sock) => sock,
        Err(e) => { println!("{:?}",e);panic!("no zmq");}
    };
    sock.bind(addr);
    
    for arg in args.arg_resource {
        println!("Fetching {}",arg);
        let url = args.flag_baseurl.clone() +&arg;
        let h = r.clone();
        let j = thread::spawn( move||{
            
            let buf =  get_content(&url,h);
            
            let b = match buf {
                Ok(b) => b,
                Err(e) => panic!("oops")
            };
            // Un-needed if we don't filter any JSON content before
            // relaying straight to VoltTron through ZMQ.
            let value: serde_json::Value = serde_json::from_str(&b).unwrap();
            println!("SERDE {:?}",value);
            let s = format!("{} {}",&arg,&b);
            s
        });
        joins.push(j);
        //let decoded: User = json::decode(buf).unwrap();
    }
    for x in joins {
        let j = match x.join () {
            Ok(j)=>j,
            Err(_)=>panic!("join")
        };
        match sock.send_str(&j, 0) {
            Ok(()) => (),
            Err(e) => panic!(e)
        }
    }
}
