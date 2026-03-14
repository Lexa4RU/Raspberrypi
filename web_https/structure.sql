--
-- Table structure for table `battle_pass`
--

DROP TABLE IF EXISTS `battle_pass`;
CREATE TABLE `battle_pass` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `slug` varchar(120) NOT NULL,
  `start_date` date NOT NULL,
  `end_date` date NOT NULL,
  `article_link` varchar(200) DEFAULT NULL,
  `chapters` int(11) NOT NULL,
  `stages_per_chapter` int(11) NOT NULL,
  `points_per_stage` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `slug` (`slug`)
);

--
-- Table structure for table `battle_pass_tanks`
--

DROP TABLE IF EXISTS `battle_pass_tanks`;
CREATE TABLE `battle_pass_tanks` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `bp_id` int(11) NOT NULL,
  `tank_wg_id` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `bp_id` (`bp_id`),
  CONSTRAINT `battle_pass_tanks_ibfk_1` FOREIGN KEY (`bp_id`) REFERENCES `battle_pass` (`id`)
);

--
-- Table structure for table `bp_data`
--

DROP TABLE IF EXISTS `bp_data`;
CREATE TABLE `bp_data` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `category` varchar(50) NOT NULL,
  `name` varchar(100) NOT NULL,
  `gold_price` decimal(30,10) DEFAULT NULL,
  PRIMARY KEY (`id`)
);

--
-- Table structure for table `bp_objects`
--

DROP TABLE IF EXISTS `bp_objects`;
CREATE TABLE `bp_objects` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `bp_id` int(11) NOT NULL,
  `data_id` int(11) NOT NULL,
  `quantity` int(11) NOT NULL,
  `reward` int(11) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `bp_id` (`bp_id`),
  KEY `data_id` (`data_id`),
  CONSTRAINT `bp_objects_ibfk_1` FOREIGN KEY (`bp_id`) REFERENCES `battle_pass` (`id`),
  CONSTRAINT `bp_objects_ibfk_2` FOREIGN KEY (`data_id`) REFERENCES `bp_data` (`id`)
);

--
-- Table structure for table `moes`
--

DROP TABLE IF EXISTS `moes`;
CREATE TABLE `moes` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `tank_id` int(11) DEFAULT NULL,
  `moe_number` int(11) DEFAULT NULL,
  `date_obtained` date DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `tank_id` (`tank_id`),
  CONSTRAINT `moes_ibfk_1` FOREIGN KEY (`tank_id`) REFERENCES `tanks` (`id`),
  CONSTRAINT `moes_chk_1` CHECK (`moe_number` between 1 and 3)
);

--
-- Table structure for table `nations`
--

DROP TABLE IF EXISTS `nations`;
CREATE TABLE `nations` (
  `code_nation` varchar(10) NOT NULL,
  `nom_nation` varchar(50) NOT NULL,
  PRIMARY KEY (`code_nation`)
);

--
-- Table structure for table `tanks`
--

DROP TABLE IF EXISTS `tanks`;
CREATE TABLE `tanks` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `full_name` varchar(200) NOT NULL,
  `tier` int(11) NOT NULL,
  `class` varchar(50) NOT NULL,
  `type` varchar(50) NOT NULL,
  `moe` int(11) NOT NULL,
  `nation_code` varchar(10) DEFAULT NULL,
  `mastery` int(11) NOT NULL,
  `wg_id` int(11) DEFAULT NULL,
  `txt` varchar(2048) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `nation_code` (`nation_code`),
  KEY `name` (`name`),
  CONSTRAINT `tanks_ibfk_1` FOREIGN KEY (`nation_code`) REFERENCES `nations` (`code_nation`),
  CONSTRAINT `tanks_chk_1` CHECK (`moe` between 0 and 3),
  CONSTRAINT `tanks_chk_2` CHECK (`mastery` between 0 and 4)
);

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `username` varchar(50) NOT NULL,
  `password` varchar(100) NOT NULL,
  PRIMARY KEY (`id`)
)