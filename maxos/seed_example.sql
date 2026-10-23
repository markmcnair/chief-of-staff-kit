-- Example training program (dow: 0=Sun .. 6=Sat). Replace with your own.
INSERT INTO program(dow,focus,ord,lift,sets,scheme,seat) VALUES
 (1,'Push',1,'Incline dumbbell press',3,'to 15 reps, then +5 lb',NULL),
 (1,'Push',2,'Weighted dips',3,'to 15 reps, then +10 lb',NULL),
 (3,'Pull',1,'Pull-ups',3,'to 15 reps, then +10 lb',NULL),
 (3,'Pull',2,'Chest-supported row',3,'to 15 reps, then +5 lb',NULL),
 (5,'Legs',1,'Trap bar deadlift',3,'7-10 reps, at 10 +5 lb',NULL),
 (5,'Legs',2,'Leg extension',3,'to 15 reps, then +5 lb',NULL);
INSERT INTO family_members(name,role,dob,notes) VALUES ('kid1','child',NULL,'example'),('kid2','child',NULL,'example');
