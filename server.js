var express = require('express')
var app = express()
var PythonShell = require('python-shell')

var runPyScript = function(res) {
  PythonShell.run('live_speech_output.py', function (err, result) {
    if (err) {
        console.info(err)
        res.send(`{"response":"${err}"}`)
    }
    else {
        console.info(result)
        res.send(`{"response":"${result}"}`)
    }
  })
}

app.get('/', function (req, res) {
  runPyScript(res)
})

app.listen(3000, '0.0.0.0', function () {
  console.log('Alexa Airline Spotter web service listening on port 3000!')
})
