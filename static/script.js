fetch("http://127.0.0.1:5000/menu")
      .then(res => res.json())
      .then(data => console.log(data));
