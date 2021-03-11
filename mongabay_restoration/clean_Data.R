setwd("/Users/gretacvega/Documents/GitHub/mongabay_restoration")
d = read.csv("raw_data.csv")
head(d)
summary(d)
names(d)
dim(d)
library(plyr)
library(dplyr)
library(tidyr)
library(stringr)
library(purrr)


#yes no columns
yn_vars = c(
"Has.project.partners",
"Has.explicit.location",
"Identify.deforestation.driver",
"Fire.prevention",
"Has.justification.for.approach",
"Addresses.known.threats",
"Discloses.species.used",
"Use.native.species",
"Use.exotic.species",
"Local.seedling.nurseries",
"Has.public.reports",
"Follow.up.disclosed",
"Has.community.involvement",
"Has.gender.component",
"Scientific.research.associated.with.project",
"News.articles.associated.with.project")

yn_matrix = d %>% 
  select(all_of(yn_vars)) %>% 
  as.matrix()  
yn_na_matrix = ifelse(yn_matrix == "", NA, yn_matrix)
tf_matrix = yn_na_matrix != "NO" 
d_tf = data.frame(Project.Number = d$Project.Number, as.data.frame(tf_matrix))
head(d_tf)

#columns to break comma values
"Primary.objective.purpose"
"Approach"
"Forest.Type"
# this would need some kind of loop that uses the warning to make sure no more extra columns are needed. 
# example of the error we have to avoid: 
# Expected 4 pieces. Additional pieces discarded in 9 rows [94, 155, 241, 243, 275, 280, 297, 298, 321]
split_vars = c("Primary.objective.purpose",
               "Approach",
               "Forest.Type")

split_d = d %>% 
  select(all_of(split_vars)) %>% 
  separate( 'Primary.objective.purpose', paste("pop", 1:5, sep="_"), sep=",", remove = TRUE, extra = "warn", fill = "right") %>% 
  separate("Approach", paste("app", 1:6, sep="_"), sep=",", remove = TRUE, extra = "warn", fill = "right") %>% 
  separate("Forest.Type", paste("ft", 1:3, sep="_"), sep=",", remove = TRUE, extra = "warn", fill = "right")



split_nbers = d %>% 
  select(all_of(split_vars)) %>%
  mutate(tmp_pop = ifelse(Primary.objective.purpose=="", NA, Primary.objective.purpose), 
         tmp_app = ifelse(Approach=="", NA, Approach),
         tmp_ft = ifelse(Forest.Type=="", NA, Forest.Type)) %>% 
  mutate(nber_pop = str_count(tmp_pop, ",") + 1,
         nber_app = str_count(tmp_app, ",") + 1,
         nber_ft = str_count(tmp_ft, ",") + 1) %>% 
  select(-tmp_pop, -tmp_app, -tmp_ft)


mgmt_vars = names(d)[1:8] 
temp_vars = names(d)[9:10] # in the spreadsheet partner name is in temp but it makes more sense that it is in mgmt 
spat_vars = names(d)[11:15] # 
strat_vars = names(d)[16:26] # 
fin_vars = names(d)[27:31] # in the spreadsheet Local.seedling.nurseries is in finance but makes more sense in strategy
soc_vars = names(d)[32:35] # in the spreadsheet "Follow.up.disclosed" and "Type.of.follow.up" are in social, but might make more sense in finance. We leave out the comments. 

mgmt_vars  # gives an idea of the partners
temp_vars # start and end
spat_vars # gives an idea of the size of the project -> numerical
strat_vars  # forest type, purpose, approach -> numerical and logical
fin_vars 
soc_vars 


# 1. let's get the table clean, that is with NAs where needed and the yes/no as logical
# 2. subdivide the tables in themes: spat, strat, fin and soc
d_clean = d %>% 
  select(Project.Number, all_of(spat_vars),all_of(fin_vars), all_of(strat_vars), all_of(soc_vars), -all_of(yn_vars)) %>% 
  left_join(d_tf, by = "Project.Number") %>% 
  mutate(tmp_pop = ifelse(Primary.objective.purpose=="", NA, Primary.objective.purpose), 
         tmp_app = ifelse(Approach=="", NA, Approach),
         tmp_ft = ifelse(Forest.Type=="", NA, Forest.Type)) %>% 
  mutate(nber_pop = str_count(tmp_pop, ",") + 1,
         nber_app = str_count(tmp_app, ",") + 1,
         nber_ft = str_count(tmp_ft, ",") + 1) %>% 
  select(-tmp_pop, -tmp_app, -tmp_ft, -all_of(split_vars))
summary(d_clean)


d_spat = d_clean %>% 
  select(Project.Number, all_of(spat_vars))
head(d_spat)
tf_spat = d_spat %>% 
  select(Project.Number, any_of(yn_vars)) 

d_strat = d_clean %>% 
  select(Project.Number, any_of(strat_vars), nber_pop, nber_app, nber_ft)
head(d_strat)
tf_strat = d_strat %>% 
  select(Project.Number, any_of(yn_vars))

d_fin = d_clean %>% 
  select(Project.Number, all_of(fin_vars))
head(d_fin)
tf_fin = d_fin %>% 
  select(Project.Number, any_of(yn_vars))

d_soc = d_clean %>% 
  select(Project.Number, all_of(soc_vars))
head(d_soc)
tf_soc = d_soc %>% 
  select(Project.Number, any_of(yn_vars))

library(ggplot2)
library(reshape2)

d_gg_melt =  tf_spat%>% 
  left_join(tf_strat) %>% 
  left_join(tf_fin) %>% 
  left_join(tf_soc) %>% 
  mutate(sum_spat = as.numeric(Has.explicit.location),
         sum_strat = Identify.deforestation.driver+ Fire.prevention+ Has.justification.for.approach+ Addresses.known.threats+ Discloses.species.used+ Use.native.species+ Use.exotic.species+ Local.seedling.nurseries,
         sum_fin = Has.public.reports+ Follow.up.disclosed,
         sum_soc = Has.community.involvement+ Has.gender.component+ Scientific.research.associated.with.project) %>% 
  mutate(resc_spat = (sum_spat-0)/max(sum_spat, na.rm = T),
         resc_strat = (sum_strat-0)/max(sum_strat, na.rm = T),
         resc_fin = (sum_fin-0)/max(sum_fin, na.rm = T),
         resc_soc = (sum_soc-0)/max(sum_soc, na.rm = T)) %>% 
select(-any_of(yn_vars), -sum_spat, -sum_strat, -sum_fin, -sum_soc) %>% 
  melt(id.vars = "Project.Number")
head(d_gg_melt)





ggplot(d_gg_melt %>% 
         filter(Project.Number %in% seq(1,20,1)))+
  geom_tile(aes(y = Project.Number, x = variable,  fill = variable,
                alpha = value, 
                width=0.75, height=0.75), colour = "white", size = 1)+
  scale_fill_manual(values = c("#FAC711", "#14CDD4", "#C17E90", "#9611AC"))+
  scale_y_discrete(position = "right")+
  coord_equal()+
  theme_void()+
  #theme_classic() +
  theme(panel.background = element_rect(fill = "#F2F2F2",
                                        colour = "#F2F2F2",
                                        size = 0.0, linetype = "solid"),
        legend.position = "none")




#ggplot(d_gg_melt)+
  geom_tile(aes(y = Project.Number, x = variable,  fill = variable,
                alpha = value, 
                width=0.75, height=0.75), colour = "white", size = 1)+
  scale_fill_manual(values = c("#FAC711", "#14CDD4", "#C17E90", "#9611AC"))+
  coord_equal()+
  theme_void() +
  theme(panel.background = element_rect(fill = "#F2F2F2",
                                        colour = "#F2F2F2",
                                        size = 0.5, linetype = "solid"),
        legend.position = "none")
ggsave("oscar.png", width = 6, height = 20, units = "cm", dpi = 300)
