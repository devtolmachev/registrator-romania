//! lib.rs

use pyo3::types::{IntoPyDict, PyDict};
use pyo3::prelude::*;

use std::collections::HashMap;
use reqwest::Error;
use reqwest::header::HeaderMap;
use reqwest::Client;
use reqwest::multipart::Form;
use regex::Regex;

use ua_generator::ua_list;


fn get_data_for_captcha() -> HashMap<String, String> {
    let captcha_url: &str = "https://www.google.com/recaptcha/api2/anchor?ar=1&k=6LcnPeckAAAAABfTS9aArfjlSyv7h45waYSB_LwT&co=aHR0cHM6Ly9wcm9ncmFtYXJlY2V0YXRlbmllLmV1OjQ0Mw..&hl=ru&v=DH3nyJMamEclyfe-nztbfV8S&size=invisible&cb=ulevyud5loaq";
    let regex_pattern: &str = r"(?P<endpoint>[api2|enterprise]+)\/anchor\?(?P<params>.*)";

    let re: Regex = Regex::new(&regex_pattern).unwrap();

    let mut hashmap: HashMap<_, _> = HashMap::new();
    let captures: regex::Captures<'_> = re.captures(captcha_url).unwrap();
    let endpoint: &str = captures.name("endpoint").map(|m| m.as_str()).unwrap();
    let params: &str = captures.name("params").map(|m| m.as_str()).unwrap();

    hashmap.insert("endpoint".to_string(), endpoint.to_string());
    hashmap.insert("params".to_string(), params.to_string());

    hashmap
}


pub async fn get_recaptcha_token(proxy: Option<String>) -> String {
    let base_url = "https://www.google.com/recaptcha";
        
    let session: Client;
    if proxy.is_some() {
        let p = reqwest::Proxy::http(proxy.unwrap().as_str()).unwrap();
        session = Client::builder()
            .danger_accept_invalid_certs(true)
            .proxy(p).build().unwrap();
    } else {
        session = Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    };

    let mut headers: HeaderMap = HeaderMap::new();
    headers.insert("Content-Type", "application/x-www-form-urlencoded".parse().unwrap());
    let data = get_data_for_captcha();

    let url_get = format!("{}/{}/anchor?{}", base_url, data["endpoint"], data["params"]);

    let resp_for_token = session.get(url_get)
        .headers(headers.clone()).send().await;

    let response_for_token = resp_for_token.unwrap().text().await;
    let token = response_for_token.unwrap().to_string();

    let re = Regex::new(r#""recaptcha-token" value="(.*?)""#).unwrap();
    let captchures = re.captures(&token).unwrap();
    let token = captchures.get(1).map_or("", |m| m.as_str());

    let params: HashMap<_, _> = data.get("params").unwrap()
        .split("&")
        .filter_map(|pair| {
            let mut split = pair.split('=');
            match (split.next(), split.next()) {
                (Some(key), Some(value)) => Some((key.to_string(), value.to_string())),
                _ => None,
            }
        })
        .collect();

    let post_data = format!(
        "v={}&reason=q&c={}&k={}&co={}&hl=en&size=invisible&chr=%5B89%2C64%2C27%5D&vh=13599012192&bg=!q62grYxHRvVxjUIjSFNd0mlvrZ-iCgIHAAAB6FcAAAANnAkBySdqTJGFRK7SirleWAwPVhv9-XwP8ugGSTJJgQ46-0IMBKN8HUnfPqm4sCefwxOOEURND35prc9DJYG0pbmg_jD18qC0c-lQzuPsOtUhHTtfv3--SVCcRvJWZ0V3cia65HGfUys0e1K-IZoArlxM9qZfUMXJKAFuWqZiBn-Qi8VnDqI2rRnAQcIB8Wra6xWzmFbRR2NZqF7lDPKZ0_SZBEc99_49j07ISW4X65sMHL139EARIOipdsj5js5JyM19a2TCZJtAu4XL1h0ZLfomM8KDHkcl_b0L-jW9cvAe2K2uQXKRPzruAvtjdhMdODzVWU5VawKhpmi2NCKAiCRUlJW5lToYkR_X-07AqFLY6qi4ZbJ_sSrD7fCNNYFKmLfAaxPwPmp5Dgei7KKvEQmeUEZwTQAS1p2gaBmt6SCOgId3QBfF_robIkJMcXFzj7R0G-s8rwGUSc8EQzT_DCe9SZsJyobu3Ps0-YK-W3MPWk6a69o618zPSIIQtSCor9w_oUYTLiptaBAEY03NWINhc1mmiYu2Yz5apkW_KbAp3HD3G0bhzcCIYZOGZxyJ44HdGsCJ-7ZFTcEAUST-aLbS-YN1AyuC7ClFO86CMICVDg6aIDyCJyIcaJXiN-bN5xQD_NixaXatJy9Mx1XEnU4Q7E_KISDJfKUhDktK5LMqBJa-x1EIOcY99E-eyry7crf3-Hax3Uj-e-euzRwLxn2VB1Uki8nqJQVYUgcjlVXQhj1X7tx4jzUb0yB1TPU9uMBtZLRvMCRKvFdnn77HgYs5bwOo2mRECiFButgigKXaaJup6NM4KRUevhaDtnD6aJ8ZWQZTXz_OJ74a_OvPK9eD1_5pTG2tUyYNSyz-alhvHdMt5_MAdI3op4ZmcvBQBV9VC2JLjphDuTW8eW_nuK9hN17zin6vjEL8YIm_MekB_dIUK3T1Nbyqmyzigy-Lg8tRL6jSinzdwOTc9hS5SCsPjMeiblc65aJC8AKmA5i80f-6Eg4BT305UeXKI3QwhI3ZJyyQAJTata41FoOXl3EF9Pyy8diYFK2G-CS8lxEpV7jcRYduz4tEPeCpBxU4O_KtM2iv4STkwO4Z_-c-fMLlYu9H7jiFnk6Yh8XlPE__3q0FHIBFf15zVSZ3qroshYiHBMxM5BVQBOExbjoEdYKx4-m9c23K3suA2sCkxHytptG-6yhHJR3EyWwSRTY7OpX_yvhbFri0vgchw7U6ujyoXeCXS9N4oOoGYpS5OyFyRPLxJH7yjXOG2Play5HJ91LL6J6qg1iY8MIq9XQtiVZHadVpZVlz3iKcX4vXcQ3rv_qQwhntObGXPAGJWEel5OiJ1App7mWy961q3mPg9aDEp9VLKU5yDDw1xf6tOFMwg2Q-PNDaKXAyP_FOkxOjnu8dPhuKGut6cJr449BKDwbnA9BOomcVSztEzHGU6HPXXyNdZbfA6D12f5lWxX2B_pobw3a1gFLnO6mWaNRuK1zfzZcfGTYMATf6d7sj9RcKNS230XPHWGaMlLmNxsgXkEN7a9PwsSVwcKdHg_HU4vYdRX6vkEauOIwVPs4dS7yZXmtvbDaX1zOU4ZYWg0T42sT3nIIl9M2EeFS5Rqms_YzNp8J-YtRz1h5RhtTTNcA5jX4N-xDEVx-vD36bZVzfoMSL2k85PKv7pQGLH-0a3DsR0pePCTBWNORK0g_RZCU_H898-nT1syGzNKWGoPCstWPRvpL9cnHRPM1ZKemRn0nPVm9Bgo0ksuUijgXc5yyrf5K49UU2J5JgFYpSp7aMGOUb1ibrj2sr-D63d61DtzFJ2mwrLm_KHBiN_ECpVhDsRvHe5iOx_APHtImevOUxghtkj-8RJruPgkTVaML2MEDOdL_UYaldeo-5ckZo3VHss7IpLArGOMTEd0bSH8tA8CL8RLQQeSokOMZ79Haxj8yE0EAVZ-k9-O72mmu5I0wH5IPgapNvExeX6O1l3mC4MqLhKPdOZOnTiEBlSrV4ZDH_9fhLUahe5ocZXvXqrud9QGNeTpZsSPeIYubeOC0sOsuqk10sWB7NP-lhifWeDob-IK1JWcgFTytVc99RkZTjUcdG9t8prPlKAagZIsDr1TiX3dy8sXKZ7d9EXQF5P_rHJ8xvmUtCWqbc3V5jL-qe8ANypwHsuva75Q6dtqoBR8vCE5xWgfwB0GzR3Xi_l7KDTsYAQIrDZVyY1UxdzWBwJCrvDrtrNsnt0S7BhBJ4ATCrW5VFPqXyXRiLxHCIv9zgo-NdBZQ4hEXXxMtbem3KgYUB1Rals1bbi8X8MsmselnHfY5LdOseyXWIR2QcrANSAypQUAhwVpsModw7HMdXgV9Uc-HwCMWafOChhBr88tOowqVHttPtwYorYrzriXNRt9LkigESMy1bEDx79CJguitwjQ9IyIEu8quEQb_-7AEXrfDzl_FKgASnnZLrAfZMtgyyddIhBpgAvgR_c8a8Nuro-RGV0aNuunVg8NjL8binz9kgmZvOS38QaP5anf2vgzJ9wC0ZKDg2Ad77dPjBCiCRtVe_dqm7FDA_cS97DkAwVfFawgce1wfWqsrjZvu4k6x3PAUH1UNzQUxVgOGUbqJsaFs3GZIMiI8O6-tZktz8i8oqpr0RjkfUhw_I2szHF3LM20_bFwhtINwg0rZxRTrg4il-_q7jDnVOTqQ7fdgHgiJHZw_OOB7JWoRW6ZlJmx3La8oV93fl1wMGNrpojSR0b6pc8SThsKCUgoY6zajWWa3CesX1ZLUtE7Pfk9eDey3stIWf2acKolZ9fU-gspeACUCN20EhGT-HvBtNBGr_xWk1zVJBgNG29olXCpF26eXNKNCCovsILNDgH06vulDUG_vR5RrGe5LsXksIoTMYsCUitLz4HEehUOd9mWCmLCl00eGRCkwr9EB557lyr7mBK2KPgJkXhNmmPSbDy6hPaQ057zfAd5s_43UBCMtI-aAs5NN4TXHd6IlLwynwc1zsYOQ6z_HARlcMpCV9ac-8eOKsaepgjOAX4YHfg3NekrxA2ynrvwk9U-gCtpxMJ4f1cVx3jExNlIX5LxE46FYIhQ",
        params["v"], token, params["k"], params["co"]
    );

    let url_post = format!(
        "{}/{}/reload?k={}",
        base_url, data["endpoint"], params["k"]
    );

    let resp = session.post(url_post)
        .body(post_data)
        .headers(headers.clone())
        .send().await;

    let response: String = resp.unwrap().text().await.unwrap();
    let result = Regex::new(r#""rresp","(.*?)""#).unwrap()
        .captures(&response)
        .unwrap()
        .get(1).map_or("", |m| m.as_str());

    result.to_string()
}



pub fn get_recaptcha_token_sync(proxy: Option<String>) -> String {
    let base_url = "https://www.google.com/recaptcha";
        
    let session: reqwest::blocking::Client;
    if proxy.is_some() {
        let p = reqwest::Proxy::http(proxy.unwrap().as_str()).unwrap();
        session = reqwest::blocking::Client::builder()
            .danger_accept_invalid_certs(true)
            .proxy(p).build().unwrap();
    } else {
        session = reqwest::blocking::Client::builder()
            .danger_accept_invalid_certs(true).build().unwrap();
    };

    let mut headers: HeaderMap = HeaderMap::new();
    headers.insert("Content-Type", "application/x-www-form-urlencoded".parse().unwrap());
    let data = get_data_for_captcha();

    let url_get = format!("{}/{}/anchor?{}", base_url, data["endpoint"], data["params"]);

    let resp_for_token = session.get(url_get)
        .headers(headers.clone()).send();

    let response_for_token = resp_for_token.unwrap().text();
    let token = response_for_token.unwrap().to_string();

    let re = Regex::new(r#""recaptcha-token" value="(.*?)""#).unwrap();
    let captchures = re.captures(&token).unwrap();
    let token = captchures.get(1).map_or("", |m| m.as_str());

    let params: HashMap<_, _> = data.get("params").unwrap()
        .split("&")
        .filter_map(|pair| {
            let mut split = pair.split('=');
            match (split.next(), split.next()) {
                (Some(key), Some(value)) => Some((key.to_string(), value.to_string())),
                _ => None,
            }
        })
        .collect();

    let post_data = format!(
        "v={}&reason=q&c={}&k={}&co={}&hl=en&size=invisible&chr=%5B89%2C64%2C27%5D&vh=13599012192&bg=!q62grYxHRvVxjUIjSFNd0mlvrZ-iCgIHAAAB6FcAAAANnAkBySdqTJGFRK7SirleWAwPVhv9-XwP8ugGSTJJgQ46-0IMBKN8HUnfPqm4sCefwxOOEURND35prc9DJYG0pbmg_jD18qC0c-lQzuPsOtUhHTtfv3--SVCcRvJWZ0V3cia65HGfUys0e1K-IZoArlxM9qZfUMXJKAFuWqZiBn-Qi8VnDqI2rRnAQcIB8Wra6xWzmFbRR2NZqF7lDPKZ0_SZBEc99_49j07ISW4X65sMHL139EARIOipdsj5js5JyM19a2TCZJtAu4XL1h0ZLfomM8KDHkcl_b0L-jW9cvAe2K2uQXKRPzruAvtjdhMdODzVWU5VawKhpmi2NCKAiCRUlJW5lToYkR_X-07AqFLY6qi4ZbJ_sSrD7fCNNYFKmLfAaxPwPmp5Dgei7KKvEQmeUEZwTQAS1p2gaBmt6SCOgId3QBfF_robIkJMcXFzj7R0G-s8rwGUSc8EQzT_DCe9SZsJyobu3Ps0-YK-W3MPWk6a69o618zPSIIQtSCor9w_oUYTLiptaBAEY03NWINhc1mmiYu2Yz5apkW_KbAp3HD3G0bhzcCIYZOGZxyJ44HdGsCJ-7ZFTcEAUST-aLbS-YN1AyuC7ClFO86CMICVDg6aIDyCJyIcaJXiN-bN5xQD_NixaXatJy9Mx1XEnU4Q7E_KISDJfKUhDktK5LMqBJa-x1EIOcY99E-eyry7crf3-Hax3Uj-e-euzRwLxn2VB1Uki8nqJQVYUgcjlVXQhj1X7tx4jzUb0yB1TPU9uMBtZLRvMCRKvFdnn77HgYs5bwOo2mRECiFButgigKXaaJup6NM4KRUevhaDtnD6aJ8ZWQZTXz_OJ74a_OvPK9eD1_5pTG2tUyYNSyz-alhvHdMt5_MAdI3op4ZmcvBQBV9VC2JLjphDuTW8eW_nuK9hN17zin6vjEL8YIm_MekB_dIUK3T1Nbyqmyzigy-Lg8tRL6jSinzdwOTc9hS5SCsPjMeiblc65aJC8AKmA5i80f-6Eg4BT305UeXKI3QwhI3ZJyyQAJTata41FoOXl3EF9Pyy8diYFK2G-CS8lxEpV7jcRYduz4tEPeCpBxU4O_KtM2iv4STkwO4Z_-c-fMLlYu9H7jiFnk6Yh8XlPE__3q0FHIBFf15zVSZ3qroshYiHBMxM5BVQBOExbjoEdYKx4-m9c23K3suA2sCkxHytptG-6yhHJR3EyWwSRTY7OpX_yvhbFri0vgchw7U6ujyoXeCXS9N4oOoGYpS5OyFyRPLxJH7yjXOG2Play5HJ91LL6J6qg1iY8MIq9XQtiVZHadVpZVlz3iKcX4vXcQ3rv_qQwhntObGXPAGJWEel5OiJ1App7mWy961q3mPg9aDEp9VLKU5yDDw1xf6tOFMwg2Q-PNDaKXAyP_FOkxOjnu8dPhuKGut6cJr449BKDwbnA9BOomcVSztEzHGU6HPXXyNdZbfA6D12f5lWxX2B_pobw3a1gFLnO6mWaNRuK1zfzZcfGTYMATf6d7sj9RcKNS230XPHWGaMlLmNxsgXkEN7a9PwsSVwcKdHg_HU4vYdRX6vkEauOIwVPs4dS7yZXmtvbDaX1zOU4ZYWg0T42sT3nIIl9M2EeFS5Rqms_YzNp8J-YtRz1h5RhtTTNcA5jX4N-xDEVx-vD36bZVzfoMSL2k85PKv7pQGLH-0a3DsR0pePCTBWNORK0g_RZCU_H898-nT1syGzNKWGoPCstWPRvpL9cnHRPM1ZKemRn0nPVm9Bgo0ksuUijgXc5yyrf5K49UU2J5JgFYpSp7aMGOUb1ibrj2sr-D63d61DtzFJ2mwrLm_KHBiN_ECpVhDsRvHe5iOx_APHtImevOUxghtkj-8RJruPgkTVaML2MEDOdL_UYaldeo-5ckZo3VHss7IpLArGOMTEd0bSH8tA8CL8RLQQeSokOMZ79Haxj8yE0EAVZ-k9-O72mmu5I0wH5IPgapNvExeX6O1l3mC4MqLhKPdOZOnTiEBlSrV4ZDH_9fhLUahe5ocZXvXqrud9QGNeTpZsSPeIYubeOC0sOsuqk10sWB7NP-lhifWeDob-IK1JWcgFTytVc99RkZTjUcdG9t8prPlKAagZIsDr1TiX3dy8sXKZ7d9EXQF5P_rHJ8xvmUtCWqbc3V5jL-qe8ANypwHsuva75Q6dtqoBR8vCE5xWgfwB0GzR3Xi_l7KDTsYAQIrDZVyY1UxdzWBwJCrvDrtrNsnt0S7BhBJ4ATCrW5VFPqXyXRiLxHCIv9zgo-NdBZQ4hEXXxMtbem3KgYUB1Rals1bbi8X8MsmselnHfY5LdOseyXWIR2QcrANSAypQUAhwVpsModw7HMdXgV9Uc-HwCMWafOChhBr88tOowqVHttPtwYorYrzriXNRt9LkigESMy1bEDx79CJguitwjQ9IyIEu8quEQb_-7AEXrfDzl_FKgASnnZLrAfZMtgyyddIhBpgAvgR_c8a8Nuro-RGV0aNuunVg8NjL8binz9kgmZvOS38QaP5anf2vgzJ9wC0ZKDg2Ad77dPjBCiCRtVe_dqm7FDA_cS97DkAwVfFawgce1wfWqsrjZvu4k6x3PAUH1UNzQUxVgOGUbqJsaFs3GZIMiI8O6-tZktz8i8oqpr0RjkfUhw_I2szHF3LM20_bFwhtINwg0rZxRTrg4il-_q7jDnVOTqQ7fdgHgiJHZw_OOB7JWoRW6ZlJmx3La8oV93fl1wMGNrpojSR0b6pc8SThsKCUgoY6zajWWa3CesX1ZLUtE7Pfk9eDey3stIWf2acKolZ9fU-gspeACUCN20EhGT-HvBtNBGr_xWk1zVJBgNG29olXCpF26eXNKNCCovsILNDgH06vulDUG_vR5RrGe5LsXksIoTMYsCUitLz4HEehUOd9mWCmLCl00eGRCkwr9EB557lyr7mBK2KPgJkXhNmmPSbDy6hPaQ057zfAd5s_43UBCMtI-aAs5NN4TXHd6IlLwynwc1zsYOQ6z_HARlcMpCV9ac-8eOKsaepgjOAX4YHfg3NekrxA2ynrvwk9U-gCtpxMJ4f1cVx3jExNlIX5LxE46FYIhQ",
        params["v"], token, params["k"], params["co"]
    );

    let url_post = format!(
        "{}/{}/reload?k={}",
        base_url, data["endpoint"], params["k"]
    );

    let resp = session.post(url_post)
        .body(post_data)
        .headers(headers.clone())
        .send();

    let response: String = resp.unwrap().text().unwrap();
    let result = Regex::new(r#""rresp","(.*?)""#).unwrap()
        .captures(&response)
        .unwrap()
        .get(1).map_or("", |m| m.as_str());

    result.to_string()
}


pub async fn make_registration(
    user_data: HashMap<String, String>,
    tip_formular: u32, 
    registration_date: String,
    mut g_recaptcha_response: Option<String>,
    proxy: Option<String>
) -> String {
    let session: Client;
    let arg;

    if proxy.is_some() {
        let p = reqwest::Proxy::http(proxy.clone().unwrap().as_str()).unwrap();
        session = Client::builder()
            .danger_accept_invalid_certs(true)
            .proxy(p).build().unwrap();
        arg = Some(proxy.clone().unwrap());

    } else {
        session = Client::builder().danger_accept_invalid_certs(true).build().unwrap();
        arg = None;
    };
    
    if g_recaptcha_response.is_none() {
        g_recaptcha_response = Some(get_recaptcha_token(arg).await.to_string());
    }
    
    let mut hashmap = HashMap::new();
        
    for (key, value) in user_data.iter() {
        // Extracting key and value as strings
        let key: String = key.to_string();
        let value: String = value.to_string();
        hashmap.insert(key, value);
    };
    
    let mut data: HashMap<&str, String> = HashMap::new();
    data.insert("tip_formular", tip_formular.to_string());
    data.insert("nume_pasaport", hashmap["Nume Pasaport"].trim().to_string());
    data.insert("data_nasterii", hashmap["Data nasterii"].trim().to_string());
    data.insert("prenume_pasaport", hashmap["Prenume Pasaport"].trim().to_string());
    data.insert("locul_nasterii", hashmap["Locul naşterii"].trim().to_string());
    data.insert("prenume_mama", hashmap["Prenume Mama"].trim().to_string());
    data.insert("prenume_tata", hashmap["Prenume Tata"].trim().to_string());
    data.insert("email", hashmap["Adresa de email"].trim().to_string());
    data.insert("numar_pasaport", hashmap["Serie și număr Pașaport"].trim().to_string());
    data.insert("data_programarii", registration_date.trim().to_string());
    data.insert("gdpr", "1".to_string());
    data.insert("honeypot", "".to_string());
    data.insert("g-recaptcha-response", g_recaptcha_response.unwrap().to_string());
    
    let url = "https://programarecetatenie.eu/programare_online";
    let headers = get_headers();

    let mut form = Form::new();

    let form_data: Vec<(String, String)> = data.iter()
        .map(|(&k, v)| (k.to_string(), v.to_string()))
        .collect();

    for (k, v) in form_data.iter() {
        form = form.text(k.clone(), v.clone());
    }

    let req_builder = session.post(url)
        .headers(headers)
        .multipart(form);

    let resp = req_builder.send().await.unwrap();
    let response = resp.text().await.unwrap();
    // println!("{} {}", response, arg.unwrap_or("".to_string()));

    response
    
}


pub fn make_registration_sync(
    user_data: HashMap<String, String>,
    tip_formular: u32, 
    registration_date: String,
    mut g_recaptcha_response: Option<String>,
    proxy: Option<String>
) -> String {
    let session: reqwest::blocking::Client;
    let arg;

    if proxy.is_some() {
        let p = reqwest::Proxy::http(proxy.clone().unwrap().as_str()).unwrap();
        session = reqwest::blocking::Client::builder()
            .danger_accept_invalid_certs(true)
            .proxy(p).build().unwrap();
        arg = Some(proxy.clone().unwrap());

    } else {
        session = reqwest::blocking::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
        arg = None;
    };
    
    if g_recaptcha_response.is_none() {
        g_recaptcha_response = Some(get_recaptcha_token_sync(arg).to_string());
    }
    
    let mut hashmap = HashMap::new();
        
    for (key, value) in user_data.iter() {
        // Extracting key and value as strings
        let key: String = key.to_string();
        let value: String = value.to_string();
        hashmap.insert(key, value);
    };
    
    let mut data: HashMap<&str, String> = HashMap::new();
    data.insert("tip_formular", tip_formular.to_string());
    data.insert("nume_pasaport", hashmap["Nume Pasaport"].trim().to_string());
    data.insert("data_nasterii", hashmap["Data nasterii"].trim().to_string());
    data.insert("prenume_pasaport", hashmap["Prenume Pasaport"].trim().to_string());
    data.insert("locul_nasterii", hashmap["Locul naşterii"].trim().to_string());
    data.insert("prenume_mama", hashmap["Prenume Mama"].trim().to_string());
    data.insert("prenume_tata", hashmap["Prenume Tata"].trim().to_string());
    data.insert("email", hashmap["Adresa de email"].trim().to_string());
    data.insert("numar_pasaport", hashmap["Serie și număr Pașaport"].trim().to_string());
    data.insert("data_programarii", registration_date.trim().to_string());
    data.insert("gdpr", "1".to_string());
    data.insert("honeypot", "".to_string());
    data.insert("g-recaptcha-response", g_recaptcha_response.unwrap().to_string());
    
    let url = "https://programarecetatenie.eu/programare_online";
    let headers = get_headers();

    let mut form: reqwest::blocking::multipart::Form = reqwest::blocking::multipart::Form::new();

    let form_data: Vec<(String, String)> = data.iter()
        .map(|(&k, v)| (k.to_string(), v.to_string()))
        .collect();

    for (k, v) in form_data.iter() {
        form = form.text(k.clone(), v.clone());
    }

    let req_builder = session.post(url)
        .headers(headers)
        .multipart(form);

    let resp = req_builder.send().unwrap();
    let response = resp.text().unwrap();
    // println!("{} {}", response, arg.unwrap_or("".to_string()));

    response
    
}


#[pyclass]
struct CaptchaPasser {
    client: Client,
}

#[pymethods]
impl CaptchaPasser {
    #[new]
    fn new() -> Self {
        let client = Client::builder().danger_accept_invalid_certs(true).build().unwrap();
        CaptchaPasser { client }
    }

    #[pyo3(signature = (proxy=None))]
    pub fn get_recaptcha_token<'a>(
        &self,
        py: Python<'a>,
        proxy: Option<String>
    ) -> Result<&'a pyo3::PyAny, PyErr> {
        let base_url = "https://www.google.com/recaptcha";
        
        let session: Client;
        if proxy.is_some() {
            let p = reqwest::Proxy::http(proxy.unwrap().as_str()).unwrap();
            session = Client::builder()
                .danger_accept_invalid_certs(true)
                .proxy(p).build().unwrap();
        } else {
            session = self.client.clone();
        };

        let mut headers: HeaderMap = HeaderMap::new();
        headers.insert("Content-Type", "application/x-www-form-urlencoded".parse().unwrap());
        let data = get_data_for_captcha();

        let url_get = format!("{}/{}/anchor?{}", base_url, data["endpoint"], data["params"]);

        pyo3_asyncio::tokio::future_into_py(py, async move {
            let resp_for_token = session.get(url_get)
                .headers(headers.clone()).send().await;
    
            let response_for_token = resp_for_token.unwrap().text().await;
            let token = response_for_token.unwrap().to_string();
    
            let re = Regex::new(r#""recaptcha-token" value="(.*?)""#).unwrap();
            let captchures = re.captures(&token).unwrap();
            let token = captchures.get(1).map_or("", |m| m.as_str());
    
            let params: HashMap<_, _> = data.get("params").unwrap()
                .split("&")
                .filter_map(|pair| {
                    let mut split = pair.split('=');
                    match (split.next(), split.next()) {
                        (Some(key), Some(value)) => Some((key.to_string(), value.to_string())),
                        _ => None,
                    }
                })
                .collect();
    
            let post_data = format!(
                "v={}&reason=q&c={}&k={}&co={}&hl=en&size=invisible&chr=%5B89%2C64%2C27%5D&vh=13599012192&bg=!q62grYxHRvVxjUIjSFNd0mlvrZ-iCgIHAAAB6FcAAAANnAkBySdqTJGFRK7SirleWAwPVhv9-XwP8ugGSTJJgQ46-0IMBKN8HUnfPqm4sCefwxOOEURND35prc9DJYG0pbmg_jD18qC0c-lQzuPsOtUhHTtfv3--SVCcRvJWZ0V3cia65HGfUys0e1K-IZoArlxM9qZfUMXJKAFuWqZiBn-Qi8VnDqI2rRnAQcIB8Wra6xWzmFbRR2NZqF7lDPKZ0_SZBEc99_49j07ISW4X65sMHL139EARIOipdsj5js5JyM19a2TCZJtAu4XL1h0ZLfomM8KDHkcl_b0L-jW9cvAe2K2uQXKRPzruAvtjdhMdODzVWU5VawKhpmi2NCKAiCRUlJW5lToYkR_X-07AqFLY6qi4ZbJ_sSrD7fCNNYFKmLfAaxPwPmp5Dgei7KKvEQmeUEZwTQAS1p2gaBmt6SCOgId3QBfF_robIkJMcXFzj7R0G-s8rwGUSc8EQzT_DCe9SZsJyobu3Ps0-YK-W3MPWk6a69o618zPSIIQtSCor9w_oUYTLiptaBAEY03NWINhc1mmiYu2Yz5apkW_KbAp3HD3G0bhzcCIYZOGZxyJ44HdGsCJ-7ZFTcEAUST-aLbS-YN1AyuC7ClFO86CMICVDg6aIDyCJyIcaJXiN-bN5xQD_NixaXatJy9Mx1XEnU4Q7E_KISDJfKUhDktK5LMqBJa-x1EIOcY99E-eyry7crf3-Hax3Uj-e-euzRwLxn2VB1Uki8nqJQVYUgcjlVXQhj1X7tx4jzUb0yB1TPU9uMBtZLRvMCRKvFdnn77HgYs5bwOo2mRECiFButgigKXaaJup6NM4KRUevhaDtnD6aJ8ZWQZTXz_OJ74a_OvPK9eD1_5pTG2tUyYNSyz-alhvHdMt5_MAdI3op4ZmcvBQBV9VC2JLjphDuTW8eW_nuK9hN17zin6vjEL8YIm_MekB_dIUK3T1Nbyqmyzigy-Lg8tRL6jSinzdwOTc9hS5SCsPjMeiblc65aJC8AKmA5i80f-6Eg4BT305UeXKI3QwhI3ZJyyQAJTata41FoOXl3EF9Pyy8diYFK2G-CS8lxEpV7jcRYduz4tEPeCpBxU4O_KtM2iv4STkwO4Z_-c-fMLlYu9H7jiFnk6Yh8XlPE__3q0FHIBFf15zVSZ3qroshYiHBMxM5BVQBOExbjoEdYKx4-m9c23K3suA2sCkxHytptG-6yhHJR3EyWwSRTY7OpX_yvhbFri0vgchw7U6ujyoXeCXS9N4oOoGYpS5OyFyRPLxJH7yjXOG2Play5HJ91LL6J6qg1iY8MIq9XQtiVZHadVpZVlz3iKcX4vXcQ3rv_qQwhntObGXPAGJWEel5OiJ1App7mWy961q3mPg9aDEp9VLKU5yDDw1xf6tOFMwg2Q-PNDaKXAyP_FOkxOjnu8dPhuKGut6cJr449BKDwbnA9BOomcVSztEzHGU6HPXXyNdZbfA6D12f5lWxX2B_pobw3a1gFLnO6mWaNRuK1zfzZcfGTYMATf6d7sj9RcKNS230XPHWGaMlLmNxsgXkEN7a9PwsSVwcKdHg_HU4vYdRX6vkEauOIwVPs4dS7yZXmtvbDaX1zOU4ZYWg0T42sT3nIIl9M2EeFS5Rqms_YzNp8J-YtRz1h5RhtTTNcA5jX4N-xDEVx-vD36bZVzfoMSL2k85PKv7pQGLH-0a3DsR0pePCTBWNORK0g_RZCU_H898-nT1syGzNKWGoPCstWPRvpL9cnHRPM1ZKemRn0nPVm9Bgo0ksuUijgXc5yyrf5K49UU2J5JgFYpSp7aMGOUb1ibrj2sr-D63d61DtzFJ2mwrLm_KHBiN_ECpVhDsRvHe5iOx_APHtImevOUxghtkj-8RJruPgkTVaML2MEDOdL_UYaldeo-5ckZo3VHss7IpLArGOMTEd0bSH8tA8CL8RLQQeSokOMZ79Haxj8yE0EAVZ-k9-O72mmu5I0wH5IPgapNvExeX6O1l3mC4MqLhKPdOZOnTiEBlSrV4ZDH_9fhLUahe5ocZXvXqrud9QGNeTpZsSPeIYubeOC0sOsuqk10sWB7NP-lhifWeDob-IK1JWcgFTytVc99RkZTjUcdG9t8prPlKAagZIsDr1TiX3dy8sXKZ7d9EXQF5P_rHJ8xvmUtCWqbc3V5jL-qe8ANypwHsuva75Q6dtqoBR8vCE5xWgfwB0GzR3Xi_l7KDTsYAQIrDZVyY1UxdzWBwJCrvDrtrNsnt0S7BhBJ4ATCrW5VFPqXyXRiLxHCIv9zgo-NdBZQ4hEXXxMtbem3KgYUB1Rals1bbi8X8MsmselnHfY5LdOseyXWIR2QcrANSAypQUAhwVpsModw7HMdXgV9Uc-HwCMWafOChhBr88tOowqVHttPtwYorYrzriXNRt9LkigESMy1bEDx79CJguitwjQ9IyIEu8quEQb_-7AEXrfDzl_FKgASnnZLrAfZMtgyyddIhBpgAvgR_c8a8Nuro-RGV0aNuunVg8NjL8binz9kgmZvOS38QaP5anf2vgzJ9wC0ZKDg2Ad77dPjBCiCRtVe_dqm7FDA_cS97DkAwVfFawgce1wfWqsrjZvu4k6x3PAUH1UNzQUxVgOGUbqJsaFs3GZIMiI8O6-tZktz8i8oqpr0RjkfUhw_I2szHF3LM20_bFwhtINwg0rZxRTrg4il-_q7jDnVOTqQ7fdgHgiJHZw_OOB7JWoRW6ZlJmx3La8oV93fl1wMGNrpojSR0b6pc8SThsKCUgoY6zajWWa3CesX1ZLUtE7Pfk9eDey3stIWf2acKolZ9fU-gspeACUCN20EhGT-HvBtNBGr_xWk1zVJBgNG29olXCpF26eXNKNCCovsILNDgH06vulDUG_vR5RrGe5LsXksIoTMYsCUitLz4HEehUOd9mWCmLCl00eGRCkwr9EB557lyr7mBK2KPgJkXhNmmPSbDy6hPaQ057zfAd5s_43UBCMtI-aAs5NN4TXHd6IlLwynwc1zsYOQ6z_HARlcMpCV9ac-8eOKsaepgjOAX4YHfg3NekrxA2ynrvwk9U-gCtpxMJ4f1cVx3jExNlIX5LxE46FYIhQ",
                params["v"], token, params["k"], params["co"]
            );
    
            let url_post = format!(
                "{}/{}/reload?k={}",
                base_url, data["endpoint"], params["k"]
            );
    
            let resp = session.post(url_post)
                .body(post_data)
                .headers(headers.clone())
                .send().await;
    
            let response: String = resp.unwrap().text().await.unwrap();
            let result = Regex::new(r#""rresp","(.*?)""#).unwrap()
                .captures(&response)
                .unwrap()
                .get(1).map_or("", |m| m.as_str());
    
            Ok(result.to_string())
        })
    }

}


fn get_headers() -> HeaderMap {
    let ua_list = ua_list::agents().clone();
    let ua = fastrand::choice(ua_list).unwrap();
    let mut headers = HeaderMap::new();

    headers.insert("User-Agent", ua.parse().unwrap());
    headers.insert("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7".parse().unwrap());
    headers.insert("Accept-Language", "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6".parse().unwrap());
    headers.insert("Cache-Control", "max-age=0".parse().unwrap());
    headers.insert("Connection", "keep-alive".parse().unwrap());
    headers.insert("Origin", "https://programarecetatenie.eu".parse().unwrap());
    headers.insert("Referer", "https://programarecetatenie.eu/programare_online".parse().unwrap());
    headers.insert("Sec-Fetch-Dest", "document".parse().unwrap());
    headers.insert("Sec-Fetch-Mode", "navigate".parse().unwrap());
    headers.insert("Sec-Fetch-Site", "same-origin".parse().unwrap());
    headers.insert("Sec-Fetch-User", "?1".parse().unwrap());
    headers.insert("Upgrade-Insecure-Requests", "1".parse().unwrap());

    headers
}


#[pyclass]
struct APIRomania {
    client: Client,
    captcha_passer: CaptchaPasser
}


#[pymethods]
impl APIRomania {
    #[new]
    fn new() -> Self {
        let client: Client = Client::builder()
            .danger_accept_invalid_certs(true)
            .build().unwrap();

        let captcha_passer = CaptchaPasser::new();
        APIRomania { client, captcha_passer }
    }

    #[pyo3(signature = (user_data, tip_formular, registration_date, g_recaptcha_response=None, proxy=None))]
    pub fn make_registration<'a>(
        &self,
        py: Python<'a>,
        user_data: &PyDict,
        tip_formular: u32, 
        registration_date: String,
        g_recaptcha_response: Option<String>,
        proxy: Option<String>
    ) -> PyResult<&'a PyAny> {
        let user_extracted_data: HashMap<String, String> = user_data.extract().unwrap();
        let py_clone = py.clone();
        
        pyo3_asyncio::tokio::future_into_py(py_clone, async move {
            let response = make_registration(
                user_extracted_data.clone(),
                tip_formular, 
                registration_date.clone(), 
                g_recaptcha_response.clone(),
                proxy
            ).await;
            Ok(response)
        })

    }
    
    #[pyo3(signature = (user_data, tip_formular, registration_date, g_recaptcha_response=None, proxy=None))]
    pub fn make_registration_sync<'a>(
        &self,
        py: Python<'a>,
        user_data: &PyDict,
        tip_formular: u32, 
        registration_date: String,
        g_recaptcha_response: Option<String>,
        proxy: Option<String>
    ) -> PyResult<String> {
        let user_extracted_data: HashMap<String, String> = user_data.extract().unwrap();
        
        py.allow_threads(|| {
            let response: String = make_registration_sync(
                user_extracted_data,
                tip_formular, 
                registration_date, 
                g_recaptcha_response,
                proxy
            );
            Ok(response)
        })

    }
    
}


async fn test_it() -> Result<String, Error> {
    let api = APIRomania::new();
    let c = CaptchaPasser::new();
    
    let mut user_data: HashMap<&str, &str> = HashMap::new();
    user_data.insert("Adresa de email", "LPFVHWLh@gmail.com");
    user_data.insert("Data nasterii", "1997-10-10");
    user_data.insert("Locul naşterii", "ISTANBUL");
    user_data.insert("Nume Pasaport", "ANASZ");
    user_data.insert("Prenume Mama", "RECYE");
    user_data.insert("Prenume Pasaport", "VALEED");
    user_data.insert("Prenume Tata", "SABRI");
    user_data.insert("Serie și număr Pașaport", "U10865982");

    
    // let  token = c.get_recaptcha_token(None);
    // let res = api.make_registration(
    //     // Python::new_pool(self),
    //     PyDict::try_from(user_data), 2, "2025-01-14".to_string(), token, 
    //     Some("http://ngjIZ71RZOif:RNW78Fm5@pool.proxy.market:10005".to_string())
    // );
    
    let fut = Python::with_gil(|py| -> String {
        let proxy = Some(String::from(""));
        let res = api.make_registration(py, 
            user_data.into_py_dict(py),
            02, 
            "2025-02-06".to_string(),
            None,
            proxy
        );

        res.unwrap().to_string()
    });

    println!("{}", fut);
    let res = fut;
    
    Ok(res)
}


#[pymodule]
#[pyo3(name = "bindings2")]
fn speedup_requests(py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<CaptchaPasser>()?;
    m.add_class::<APIRomania>()?;
    Ok(())
}
