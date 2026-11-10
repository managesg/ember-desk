# Generates SAMPLE DATA for Bluebird Coffee Roasters (fictional).
import random, datetime
random.seed(7)
H="SAMPLE DATA - Bluebird Coffee Roasters (fictional)"
open("data/price_list.md","w").write(f"# {H}\nPrice list\n- Espresso $3.00\n- Latte $4.50\n- Drip coffee $2.50\n- Cold brew $4.00 (raised to $5.00 from week 5)\n- Bag of beans 12oz $16.00\n- Croissant $3.50\n")
open("data/faq.md","w").write(f"# {H}\nFAQ\nQ: Do you have oat milk? A: Yes, +$0.75.\nQ: Wifi? A: Yes, ask at the counter.\nQ: Do you ship beans? A: Within the US, $6 flat.\nQ: Hours? A: 7am-5pm daily.\nQ: Refunds? A: Remake any drink you are not happy with.\n")
rev=[(5,"Best espresso in town"),(2,"Cold brew price jumped to $5, too much"),(4,"Great latte, slow line"),(1,"No espresso for three days, went elsewhere"),(2,"Espresso machine down again? no shots on Tuesday"),(5,"Love the beans"),(3,"Cold brew was $4 now $5, hmm"),(4,"Friendly staff"),(2,"Line took 15 minutes"),(5,"Croissants are perfect"),(1,"Wanted espresso, grinder broken, sign said sorry"),(3,"Oat milk surcharge is annoying"),(4,"Nice beans, fair shipping"),(2,"Cold brew too expensive now"),(5,"Cozy spot"),(3,"Drip coffee was lukewarm"),(4,"Good value drip"),(2,"Slow service during rush"),(5,"Best croissant"),(1,"Third visit with no espresso, giving up"),(4,"Great wifi"),(3,"Price of cold brew went up a lot"),(5,"Beans arrived fast"),(4,"Lovely latte art"),(2,"Out of espresso again"),(5,"Staff remembered my order"),(3,"Parking is hard"),(4,"Solid drip"),(2,"Cold brew $5 not worth it"),(5,"Will be back")]
with open("data/reviews.csv","w") as f:
    f.write("stars,text\n"); [f.write(f'{s},"{t}"\n') for s,t in rev]
d=datetime.date(2026,9,7)
with open("data/sales.csv","w") as f:
    f.write("date,revenue_usd,espresso_drinks,cold_brew\n")
    for i in range(56):
        day=d+datetime.timedelta(i); wk=i//7+1
        esp=random.randint(70,90); cb=random.randint(30,40)
        if wk>=5: cb=int(cb*0.6)
        if wk==7 and day.weekday() in (1,2,3): esp=0
        rv=esp*3.5+cb*(5 if wk>=5 else 4)+random.randint(300,400)
        f.write(f"{day},{rv:.0f},{esp},{cb}\n")
open("data/inbox_week.md","w").write(f"# {H}\nInbox, week 8\n\nFrom: supplier@beanco.example - Invoice 4471 due Friday, $812.\nFrom: Dana (barista) - Grinder motor died Tuesday, repair guy came Friday. Sorry!\nFrom: customer - Why is cold brew $5 now?\nFrom: landlord - Rent increase notice effective January.\nFrom: customer - Do you have oat milk?\nFrom: Dana - Can I swap Saturday shift?\nFrom: marketing@spam.example - Boost your SEO!\n")
