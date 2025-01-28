# hchk-cron

## firebase rules

```
{
  "rules": {
    ".read": "auth.uid !== null",
    ".write": false, 
      "workloads": {
        "$uid": {
    			".read": "auth.uid !== null",
    			".write": "auth.uid === $uid"          
        }
      }
  }
}
```
