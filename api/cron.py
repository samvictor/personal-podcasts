def handler(req, res):
  # Your daily task logic here
  print("Daily task executed successfully")
  res.status(200).send("Success")